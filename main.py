#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《星界迴響：Gemini 4 動態劇情 2D 原生應用程式》
基於 Pygame (SDL2 原生圖形介面，非網頁)，支援：
1. Android 手機執行（透過 Pydroid 3 直接開啟，或用 Buildozer 打包為獨立 .apk）
2. Windows 筆電執行（python gemini4_native_2d_app.py，或用 PyInstaller 打包為獨立 .exe）
3. 內建背景執行緒串接 Gemini 4 Argon (gemini-4-argon) 依遊玩過程動態生成新地圖與新劇情
"""

import json
import math
import os
import sys
import threading
import time
import urllib.error
import urllib.request

try:
    import pygame
except ImportError:
    print("請先安裝 pygame：pip install pygame")
    sys.exit(1)

# ==================== 畫面與地圖常數 ====================
WIN_W, WIN_H = 960, 600
MAP_COLS, MAP_ROWS = 16, 10
TILE = 44
MAP_OFFSET_X = 20
MAP_OFFSET_Y = 64
SIDE_X = MAP_OFFSET_X + MAP_COLS * TILE + 16
SIDE_W = WIN_W - SIDE_X - 16

BIOMES = {
    "ruins": {
        "name": "星門遺跡",
        "floor1": (19, 28, 49),
        "floor2": (25, 36, 62),
        "wall": (51, 65, 85),
        "wall_top": (71, 85, 105),
        "hazard": (88, 28, 135),
        "accent": (99, 102, 241),
    },
    "forest": {
        "name": "迷霧幽林",
        "floor1": (12, 36, 29),
        "floor2": (17, 46, 37),
        "wall": (20, 83, 45),
        "wall_top": (22, 101, 52),
        "hazard": (6, 78, 59),
        "accent": (16, 185, 129),
    },
    "cyber": {
        "name": "機械方舟",
        "floor1": (15, 23, 42),
        "floor2": (30, 27, 75),
        "wall": (49, 46, 129),
        "wall_top": (67, 56, 202),
        "hazard": (30, 58, 138),
        "accent": (56, 189, 248),
    },
    "volcano": {
        "name": "緋紅熔岩",
        "floor1": (39, 18, 21),
        "floor2": (51, 22, 27),
        "wall": (127, 29, 29),
        "wall_top": (153, 27, 27),
        "hazard": (154, 52, 18),
        "accent": (249, 115, 22),
    },
}

SAVE_FILE = "gemini4_play_save.json"


# ==================== 跨平台中文字型載入器 ====================
def get_cjk_font(size: int, bold: bool = False):
    """自動尋找 Windows / Android / macOS / Linux 系統內建繁體中文字型"""
    candidate_paths = [
        # Windows
        "C:/Windows/Fonts/msjhbd.ttc" if bold else "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/msjh.ttc",
        "C:/Windows/Fonts/mingliu.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        # Android (Pydroid 3 / APK 系統字型路徑)
        "/system/fonts/NotoSansCJK-Regular.ttc",
        "/system/fonts/DroidSansFallback.ttf",
        "/system/fonts/NotoSansSC-Regular.otf",
        # Linux / macOS
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            try:
                return pygame.font.Font(path, size)
            except Exception:
                pass
    for sys_name in ["microsoftjhenghei", "notosanscjk", "pingfangtc", "heiti", "simhei", "arial"]:
        matched = pygame.font.match_font(sys_name, bold=bold)
        if matched:
            try:
                return pygame.font.Font(matched, size)
            except Exception:
                pass
    return pygame.font.Font(None, size)


# ==================== 遊戲核心狀態與存檔 ====================
class GameApp:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("星界迴響：Gemini 4 動態劇情 2D 原生版")
        self.screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()

        self.font_sm = get_cjk_font(15)
        self.font_md = get_cjk_font(17)
        self.font_lg = get_cjk_font(21, bold=True)

        self.api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        self.model = "gemini-4-argon"

        self.chapter = 1
        self.chapter_title = "遺落星門的甦醒"
        self.biome = "ruins"
        self.quest_title = "調查星門遺跡並決定守門人的命運"
        self.quest_desc = "靠近 NPC 按空白鍵或點擊「A 互動」，踏入右側紫色裂隙即可生成下一章！"

        self.hp = 100
        self.mana = 30
        self.gold = 50
        self.trait = "中立探索者"
        self.inventory = ["古舊星盤"]
        self.player_x = 2
        self.player_y = 5

        self.map_grid = []
        self.entities = []
        self.logs = [
            "🌟 歡迎來到《星界迴響》原生 2D 應用程式！",
            "👉 支援手機螢幕觸控搖桿、直接點擊地圖格子、以及電腦 WASD／方向鍵。",
            "✨ 你的每個選擇都會寫入本機存檔，並由 Gemini 4 即時生成下一章！",
        ]
        self.play_history = [
            "第 1 章開始：主角帶著「古舊星盤」在遺落星門甦醒。"
        ]
        self.floating_texts = []

        # 互動對話視窗與狀態
        self.active_entity = None
        self.is_generating = False
        self.gen_status_msg = ""

        self.touch_buttons = {}
        self.choice_rects = []

        self.init_chapter_1()
        self.load_local_save_if_exists()

    def build_grid(self, walls):
        grid = [[0 for _ in range(MAP_COLS)] for _ in range(MAP_ROWS)]
        for r in range(MAP_ROWS):
            for c in range(MAP_COLS):
                if r == 0 or r == MAP_ROWS - 1 or c == 0 or c == MAP_COLS - 1:
                    grid[r][c] = 1
        for w in walls:
            if len(w) >= 2:
                c, r = int(w[0]), int(w[1])
                t = int(w[2]) if len(w) > 2 else 1
                if 0 < r < MAP_ROWS - 1 and 0 < c < MAP_COLS - 1:
                    grid[r][c] = t
        grid[self.player_y][self.player_x] = 0
        return grid

    def init_chapter_1(self):
        self.map_grid = self.build_grid([
            [5, 2, 1], [5, 3, 1], [5, 7, 1], [5, 8, 1],
            [10, 3, 2], [10, 4, 2], [10, 5, 2], [11, 4, 1],
        ])
        self.entities = [
            {
                "id": "npc_elaine",
                "type": "npc",
                "name": "守門人艾琳",
                "color": [56, 189, 248],
                "x": 4,
                "y": 5,
                "greeting": "「旅人，你手上的古舊星盤正在發光！啟動星門會抽乾村莊結界，你打算怎麼做？」",
                "choices": [
                    {
                        "label": "1. 優先保護村莊：將星盤能量注入防禦結界（共鳴 -10，獲「守護者紋章」）",
                        "effect": {
                            "mana": -10,
                            "trait": "仁慈守護者",
                            "item": "守護者紋章",
                            "log": "選擇保護村莊結界，獲得守門人艾琳贈與的「守護者紋章」。",
                            "reply": "艾琳感激地行禮：「謝謝你！這枚紋章將在下一個世界守護你。」",
                        },
                    },
                    {
                        "label": "2. 強行超載星門：抽取結界能量開啟隱藏通道（共鳴 +25，傾向「狂熱求知者」）",
                        "effect": {
                            "mana": 25,
                            "trait": "狂熱求知者",
                            "item": "超載核心",
                            "log": "強行抽取村莊結界能量超載星門，取得「超載核心」。",
                            "reply": "星門發出劇烈轟鳴！艾琳退後一步：「小心裂隙深處的星空獵犬！」",
                        },
                    },
                    {
                        "label": "3. 邀請艾琳結伴同行：一起穿過星門尋找真相（HP +15，獲「星光提燈」）",
                        "effect": {
                            "hp": 15,
                            "trait": "羈絆領袖",
                            "item": "星光提燈",
                            "log": "說服守門人艾琳結伴同行，獲得「星光提燈」。",
                            "reply": "艾琳微笑著舉起長杖：「好！我們一起去揭開星門背後的真相！」",
                        },
                    },
                ],
            },
            {
                "id": "chest_1",
                "type": "chest",
                "name": "星塵寶箱",
                "color": [245, 158, 11],
                "x": 8,
                "y": 2,
                "greeting": "你在遺跡角落發現一個刻滿符文的古老星塵寶箱。",
                "choices": [
                    {
                        "label": "1. 用星盤共鳴溫和解鎖（星幣 +40，獲得「記憶水晶」）",
                        "effect": {
                            "gold": 40,
                            "item": "記憶水晶",
                            "log": "解開星塵寶箱，取得記錄上古秘辛的「記憶水晶」。",
                            "reply": "寶箱輕聲彈開，裡面躺著一顆閃爍的「記憶水晶」！",
                        },
                    },
                    {
                        "label": "2. 直接砸開寶箱（HP -10，星幣 +65，傾向「果斷掠奪者」）",
                        "effect": {
                            "hp": -10,
                            "gold": 65,
                            "trait": "果斷掠奪者",
                            "log": "暴力砸開寶箱，受了點輕傷但搜刮了大量星幣。",
                            "reply": "防禦符文炸開震傷了手，但你拿走了裡面所有的星幣！",
                        },
                    },
                ],
            },
            {
                "id": "mob_1",
                "type": "monster",
                "name": "失控星界哨兵",
                "color": [244, 63, 94],
                "x": 11,
                "y": 7,
                "greeting": "一台失控的星界哨兵擋在前方：「警—告—發現未授權生命體—」",
                "choices": [
                    {
                        "label": "1. 正面揮劍擊破哨兵（HP -15，星幣 +50，獲得「哨兵核心」）",
                        "effect": {
                            "hp": -15,
                            "gold": 50,
                            "item": "哨兵核心",
                            "trait": "無畏戰士",
                            "log": "正面擊破失控星界哨兵，奪得「哨兵核心」。",
                            "reply": "你精準斬斷動力核心，哨兵應聲倒地！",
                        },
                    },
                    {
                        "label": "2. 用星盤改寫其邏輯收服為夥伴（共鳴 -15，獲得「微型機械哨兵」）",
                        "effect": {
                            "mana": -15,
                            "item": "微型機械哨兵",
                            "trait": "機械親和者",
                            "log": "成功改寫哨兵邏輯，將其收服為「微型機械哨兵」夥伴。",
                            "reply": "哨兵紅光轉為柔和藍光：「邏輯重設完成，隨時聽候差遣。」",
                        },
                    },
                ],
            },
            {
                "id": "portal_next",
                "type": "portal",
                "name": "時空裂隙",
                "color": [168, 85, 247],
                "x": 14,
                "y": 5,
            },
        ]

    def save_local_state(self):
        try:
            data = {
                "chapter": self.chapter,
                "chapter_title": self.chapter_title,
                "biome": self.biome,
                "hp": self.hp,
                "mana": self.mana,
                "gold": self.gold,
                "trait": self.trait,
                "inventory": self.inventory,
                "play_history": self.play_history,
            }
            with open(SAVE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load_local_save_if_exists(self):
        if os.path.exists("gemini_api_key.txt") and not self.api_key:
            try:
                with open("gemini_api_key.txt", "r", encoding="utf-8") as f:
                    self.api_key = f.read().strip()
            except Exception:
                pass

    def add_log(self, msg: str):
        self.logs.append(msg)
        if len(self.logs) > 18:
            self.logs = self.logs[-18:]

    def add_float_text(self, gx: int, gy: int, text: str, color=(251, 191, 36)):
        px = MAP_OFFSET_X + gx * TILE + TILE // 2
        py = MAP_OFFSET_Y + gy * TILE
        self.floating_texts.append({"x": px, "y": py, "text": text, "color": color, "life": 45})

    # ==================== 角色移動與互動邏輯 ====================
    def move_player(self, dx: int, dy: int):
        if self.active_entity or self.is_generating:
            return
        nx, ny = self.player_x + dx, self.player_y + dy
        if nx < 0 or nx >= MAP_COLS or ny < 0 or ny >= MAP_ROWS:
            return
        if self.map_grid[ny][nx] == 1:
            self.add_float_text(nx, ny, "受阻", (148, 163, 184))
            return

        for ent in self.entities:
            if ent["x"] == nx and ent["y"] == ny:
                self.trigger_entity(ent)
                return

        self.player_x, self.player_y = nx, ny
        if self.map_grid[ny][nx] == 2:
            self.hp = max(1, self.hp - 2)
            self.add_float_text(nx, ny, "-2 HP 能量地形", (244, 63, 94))

    def interact_nearby(self):
        if self.active_entity or self.is_generating:
            return
        for ent in self.entities:
            if abs(ent["x"] - self.player_x) + abs(ent["y"] - self.player_y) <= 1:
                self.trigger_entity(ent)
                return
        self.add_float_text(self.player_x, self.player_y, "周圍無目標", (148, 163, 184))

    def trigger_entity(self, ent):
        if ent["type"] == "portal":
            self.start_generate_next_chapter()
            return
        self.active_entity = ent

    def apply_choice(self, ent, choice):
        eff = choice.get("effect", {})
        if eff.get("hp"):
            self.hp = max(1, min(200, self.hp + int(eff["hp"])))
            self.add_float_text(self.player_x, self.player_y, f"{eff['hp']:+d} HP", (16, 185, 129) if eff["hp"] > 0 else (244, 63, 94))
        if eff.get("mana"):
            self.mana = max(0, self.mana + int(eff["mana"]))
        if eff.get("gold"):
            self.gold = max(0, self.gold + int(eff["gold"]))
        if eff.get("trait"):
            self.trait = str(eff["trait"])
        if eff.get("item") and eff["item"] not in self.inventory:
            self.inventory.append(eff["item"])
            self.add_float_text(ent["x"], ent["y"], f"獲得 {eff['item']}", (251, 191, 36))

        log_line = eff.get("log", f"對 {ent['name']} 選擇了：{choice.get('label', '')}")
        self.play_history.append(f"第 {self.chapter} 章：{log_line}")
        self.add_log(f"👉 {log_line}")
        if eff.get("reply"):
            self.add_log(f"💬 {eff['reply']}")

        if ent["type"] in ("chest", "monster"):
            self.entities = [e for e in self.entities if e["id"] != ent["id"]]
        else:
            ent["greeting"] = eff.get("reply", "「願星界指引你的道路。」")
            ent["choices"] = [
                {
                    "label": "1. 道別並繼續探索",
                    "effect": {"log": f"與 {ent['name']} 再次交談。", "reply": f"{ent['name']} 向你點頭致意。"},
                }
            ]
        self.active_entity = None
        self.save_local_state()

    # ==================== GEMINI 4 動態章節生成 ====================
    def start_generate_next_chapter(self):
        if self.is_generating:
            return
        self.is_generating = True
        self.gen_status_msg = f"正在呼叫 {self.model} 根據你的遊玩歷程生成第 {self.chapter + 1} 章..."
        t = threading.Thread(target=self._generate_worker, daemon=True)
        t.start()

    def _call_gemini4_api(self, prompt_text: str) -> dict:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt_text}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.85,
            },
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            raw = body["candidates"][0]["content"]["parts"][0]["text"]
            cleaned = raw.strip().removeprefix("```json").removesuffix("```").strip()
            return json.loads(cleaned)

    def _generate_worker(self):
        next_num = self.chapter + 1
        data = None
        if self.api_key:
            try:
                prompt = f"""你是 2D 角色扮演遊戲《星界迴響》的動態劇本引擎（模型：{self.model}）。
請根據玩家目前的實際遊玩歷程，生成「第 {next_num} 章」的 2D 地圖與互動事件！
【玩家狀態】
- 目前章節：第 {self.chapter} 章（{self.chapter_title}）
- 生命：{self.hp}，共鳴：{self.mana}，星幣：{self.gold}，傾向：「{self.trait}」
- 背包道具：{json.dumps(self.inventory, ensure_ascii=False)}
- 過往遊玩歷程：{json.dumps(self.play_history, ensure_ascii=False)}

請回傳純 JSON 物件：
{{
  "chapterTitle": "第{next_num}章標題（6-12字）",
  "biome": "ruins, forest, cyber, volcano 四選一",
  "openingNarration": "新章節開場劇情（60-100字，明確呼應玩家上一章的選擇與背包道具）",
  "questTitle": "本章任務目標（8-14字）",
  "questDesc": "任務提示（25-45字）",
  "walls": [[6,2,1],[6,3,1],[9,6,2],[9,7,2]],
  "entities": [
    {{
      "id": "npc_{next_num}",
      "type": "npc",
      "name": "新NPC名稱",
      "x": 5,
      "y": 4,
      "greeting": "呼應玩家過去行為的開場白",
      "choices": [
        {{
          "label": "1. 選項一文字",
          "effect": {{"hp": 0, "mana": 15, "gold": 25, "trait": "新傾向", "item": "新道具名稱", "log": "紀錄摘要", "reply": "NPC回應"}}
        }},
        {{
          "label": "2. 選項二文字",
          "effect": {{"hp": -10, "mana": 25, "gold": 40, "trait": "新傾向", "item": "", "log": "紀錄摘要", "reply": "NPC回應"}}
        }}
      ]
    }},
    {{
      "id": "chest_{next_num}",
      "type": "chest",
      "name": "特殊寶箱或祭壇名稱",
      "x": 9,
      "y": 3,
      "greeting": "寶箱或祭壇描述",
      "choices": [
        {{
          "label": "1. 調查並取得寶物",
          "effect": {{"hp": 10, "mana": 15, "gold": 35, "trait": "探索傾向", "item": "新寶物", "log": "紀錄摘要", "reply": "結果描述"}}
        }}
      ]
    }},
    {{
      "id": "mob_{next_num}",
      "type": "monster",
      "name": "本章強敵名稱",
      "x": 11,
      "y": 6,
      "greeting": "強敵登場台詞",
      "choices": [
        {{
          "label": "1. 正面迎戰擊敗強敵",
          "effect": {{"hp": -15, "mana": 20, "gold": 65, "trait": "戰鬥傾向", "item": "戰利品", "log": "戰鬥結果摘要", "reply": "戰鬥結果"}}
        }},
        {{
          "label": "2. 運用背包信物智取或感化",
          "effect": {{"hp": 5, "mana": -10, "gold": 30, "trait": "智略傾向", "item": "", "log": "智取結果摘要", "reply": "智取結果"}}
        }}
      ]
    }}
  ]
}}"""
                data = self._call_gemini4_api(prompt)
            except Exception as e:
                self.add_log(f"⚠️ Gemini 4 雲端連線提示 ({e})，已自動切換內建因果劇本引擎！")

        if not data:
            data = self._fallback_dynamic_chapter(next_num)

        self._apply_new_chapter(data)
        self.is_generating = False

    def _fallback_dynamic_chapter(self, next_num: int) -> dict:
        biome_keys = ["forest", "cyber", "volcano", "ruins"]
        b_key = biome_keys[(next_num - 2) % len(biome_keys)]
        b_name = BIOMES[b_key]["name"]
        last_event = self.play_history[-1] if self.play_history else "穿越星門"
        latest_item = self.inventory[-1] if self.inventory else "古舊星盤"

        return {
            "chapterTitle": f"第 {next_num} 紀元：{b_name}的迴響",
            "biome": b_key,
            "openingNarration": f"因為你在上一章「{last_event}」，星界因果將你引導至「{b_name}」！此地的守護者已感應到你身上的「{latest_item}」。",
            "questTitle": f"解開{b_name}的因果試煉",
            "questDesc": f"善用「{latest_item}」與「{self.trait}」名號探索新區域並前往下一道裂隙。",
            "walls": [[5, 2, 1], [5, 3, 2], [8, 5, 1], [8, 6, 2], [10, 2, 1], [10, 7, 1]],
            "entities": [
                {
                    "id": f"npc_{next_num}",
                    "type": "npc",
                    "name": "星界記錄者洛伊" if b_key != "cyber" else "中樞AI零號",
                    "x": 5,
                    "y": 6,
                    "greeting": f"「原來你就是那位『{self.trait}』！我看見你帶著『{latest_item}』來到{b_name}，你準備好面對接下來的命運了嗎？」",
                    "choices": [
                        {
                            "label": f"1. 出示「{latest_item}」換取秘傳強化（共鳴 +20，獲「第{next_num}章星印」）",
                            "effect": {
                                "mana": 20,
                                "item": f"第{next_num}章星印",
                                "trait": "星界破譯者",
                                "log": f"在第 {next_num} 章出示「{latest_item}」，獲得「第{next_num}章星印」。",
                                "reply": "「這正是上古預言中的信物！收下這枚星印吧！」",
                            },
                        },
                        {
                            "label": "2. 請他為你治療並指點頭目弱點（HP +25，星幣 +35）",
                            "effect": {
                                "hp": 25,
                                "gold": 35,
                                "trait": "沉穩獵人",
                                "log": f"在第 {next_num} 章獲得治療與情報支援。",
                                "reply": "「你的傷勢已痊癒，前方領主懼怕高階星界共鳴！」",
                            },
              
