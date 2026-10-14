#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《星界迴響：Gemini 4 動態劇情 2D RPG》Android APK / Windows 雙棲原生版 (Kivy OpenGL ES 2.0)
檔名已直接設定為 main.py，可直接上傳至 GitHub 配合 Buildozer 編譯為 Android .apk！
"""

import json
import math
import os
import threading
import urllib.request

import kivy
kivy.require("2.1.0")

from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

# ==================== 註冊 Android / Windows 系統繁體中文字型 ====================
CJK_FONT = "Roboto"
for font_path in [
    "/system/fonts/NotoSansCJK-Regular.ttc",
    "/system/fonts/DroidSansFallback.ttf",
    "/system/fonts/NotoSansSC-Regular.otf",
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]:
    if os.path.exists(font_path):
        try:
            LabelBase.register(name="CJK", fn_regular=font_path)
            CJK_FONT = "CJK"
            break
        except Exception:
            pass

MAP_COLS = 14
MAP_ROWS = 9

BIOMES = {
    "ruins": {
        "name": "星門遺跡",
        "floor1": (0.08, 0.11, 0.20, 1),
        "floor2": (0.10, 0.14, 0.25, 1),
        "wall": (0.22, 0.28, 0.38, 1),
        "hazard": (0.35, 0.11, 0.53, 1),
    },
    "forest": {
        "name": "迷霧幽林",
        "floor1": (0.05, 0.15, 0.12, 1),
        "floor2": (0.07, 0.20, 0.16, 1),
        "wall": (0.09, 0.35, 0.19, 1),
        "hazard": (0.04, 0.30, 0.24, 1),
    },
    "cyber": {
        "name": "機械方舟",
        "floor1": (0.06, 0.09, 0.17, 1),
        "floor2": (0.12, 0.11, 0.30, 1),
        "wall": (0.20, 0.18, 0.51, 1),
        "hazard": (0.12, 0.23, 0.54, 1),
    },
    "volcano": {
        "name": "緋紅熔岩",
        "floor1": (0.16, 0.07, 0.09, 1),
        "floor2": (0.21, 0.09, 0.11, 1),
        "wall": (0.50, 0.12, 0.12, 1),
        "hazard": (0.65, 0.22, 0.08, 1),
    },
}


class MapCanvasWidget(Widget):
    """2D 網格地圖與角色 OpenGL 渲染元件（支援直接觸控點擊格子移動）"""

    def __init__(self, controller, **kwargs):
        super().__init__(**kwargs)
        self.controller = controller
        self.tick = 0
        self.bind(pos=self.redraw, size=self.redraw)
        Clock.schedule_interval(self._animate, 1.0 / 24.0)

    def _animate(self, dt):
        self.tick += 1
        self.redraw()

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        tile_w = self.width / MAP_COLS
        tile_h = self.height / MAP_ROWS
        gx = int((touch.x - self.x) / tile_w)
        # 轉換使 y=0 在上方，符合直覺 2D 座標
        gy = MAP_ROWS - 1 - int((touch.y - self.y) / tile_h)
        gx = max(0, min(MAP_COLS - 1, gx))
        gy = max(0, min(MAP_ROWS - 1, gy))

        dx = gx - self.controller.player_x
        dy = gy - self.controller.player_y
        if dx == 0 and dy == 0:
            self.controller.interact_nearby()
        elif abs(dx) >= abs(dy):
            self.controller.move_player(1 if dx > 0 else -1, 0)
        else:
            self.controller.move_player(0, 1 if dy > 0 else -1)
        return True

    def redraw(self, *args):
        self.canvas.clear()
        b = BIOMES.get(self.controller.biome, BIOMES["ruins"])
        tile_w = self.width / MAP_COLS
        tile_h = self.height / MAP_ROWS

        with self.canvas:
            # 1. 繪製 2D 地圖網格
            for r in range(MAP_ROWS):
                for c in range(MAP_COLS):
                    sx = self.x + c * tile_w
                    sy = self.y + (MAP_ROWS - 1 - r) * tile_h
                    cell = self.controller.map_grid[r][c]
                    if cell == 1:
                        Color(*b["wall"])
                        Rectangle(pos=(sx, sy), size=(tile_w - 1, tile_h - 1))
                    elif cell == 2:
                        Color(*b["hazard"])
                        Rectangle(pos=(sx, sy), size=(tile_w - 1, tile_h - 1))
                    else:
                        fl = b["floor1"] if (r + c) % 2 == 0 else b["floor2"]
                        Color(*fl)
                        Rectangle(pos=(sx, sy), size=(tile_w, tile_h))

            # 2. 繪製 NPC、寶箱、怪物與紫色時空裂隙
            for ent in self.controller.entities:
                ex = self.x + ent["x"] * tile_w
                ey = self.y + (MAP_ROWS - 1 - ent["y"]) * tile_h
                bounce = math.sin(self.tick * 0.15 + ent["x"]) * (tile_h * 0.06)

                if ent["type"] == "portal":
                    Color(0.66, 0.33, 0.97, 0.9)
                    Ellipse(pos=(ex + tile_w * 0.1, ey + tile_h * 0.1), size=(tile_w * 0.8, tile_h * 0.8))
                    Color(0.94, 0.67, 0.99, 1)
                    Line(circle=(ex + tile_w * 0.5, ey + tile_h * 0.5, min(tile_w, tile_h) * 0.28), width=2)
                elif ent["type"] == "chest":
                    Color(0.96, 0.62, 0.04, 1)
                    Rectangle(pos=(ex + tile_w * 0.2, ey + tile_h * 0.2), size=(tile_w * 0.6, tile_h * 0.55))
                elif ent["type"] == "monster":
                    Color(0.96, 0.25, 0.37, 1)
                    Ellipse(pos=(ex + tile_w * 0.15, ey + tile_h * 0.15 + bounce), size=(tile_w * 0.7, tile_h * 0.7))
                else:
                    Color(0.22, 0.74, 0.97, 1)
                    Ellipse(pos=(ex + tile_w * 0.2, ey + tile_h * 0.2 + bounce), size=(tile_w * 0.6, tile_h * 0.6))

            # 3. 繪製玩家角色（金色光環與藍紫勇者）
            px = self.x + self.controller.player_x * tile_w
            py = self.y + (MAP_ROWS - 1 - self.controller.player_y) * tile_h
            pb = math.sin(self.tick * 0.2) * (tile_h * 0.05)

            Color(0.39, 0.40, 0.95, 0.35)
            Ellipse(pos=(px + tile_w * 0.08, py + tile_h * 0.08), size=(tile_w * 0.84, tile_h * 0.84))
            Color(0.51, 0.55, 0.97, 1)
            Rectangle(pos=(px + tile_w * 0.25, py + tile_h * 0.15 + pb), size=(tile_w * 0.5, tile_h * 0.4))
            Color(0.99, 0.90, 0.54, 1)
            Ellipse(pos=(px + tile_w * 0.28, py + tile_h * 0.50 + pb), size=(tile_w * 0.44, tile_h * 0.4))


class Gemini4RpgApp(App):
    def build(self):
        self.title = "星界迴響：Gemini 4 動態 2D RPG"
        Window.clearcolor = (0.04, 0.05, 0.09, 1)

        self.api_key = ""
        self.model = "gemini-4-argon"
        self.chapter = 1
        self.chapter_title = "遺落星門的甦醒"
        self.biome = "ruins"
        self.hp = 100
        self.mana = 30
        self.gold = 50
        self.trait = "中立探索者"
        self.inventory = ["古舊星盤"]
        self.player_x = 2
        self.player_y = 4
        self.play_history = ["第 1 章開始：帶著古舊星盤在星門遺跡甦醒。"]

        self.map_grid = []
        self.entities = []
        self._load_saved_key()
        self._init_chapter_1()

        # 主版面配置
        root = BoxLayout(orientation="vertical", padding=6, spacing=6)

        # 1. 頂部狀態列
        top_bar = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=6)
        self.hud_label = Label(
            text="",
            font_name=CJK_FONT,
            font_size="14sp",
            color=(0.95, 0.96, 0.98, 1),
            halign="left",
            valign="middle",
        )
        self.hud_label.bind(size=self.hud_label.setter("text_size"))
        btn_key = Button(
            text="API 金鑰設定",
            font_name=CJK_FONT,
            font_size="13sp",
            size_hint_x=None,
            width=120,
            background_color=(0.31, 0.27, 0.90, 1),
        )
        btn_key.bind(on_release=lambda *_: self.open_api_key_popup())
        top_bar.add_widget(self.hud_label)
        top_bar.add_widget(btn_key)
        root.add_widget(top_bar)

        # 2. 中央區域（左側 2D 地圖 + 右側劇情紀錄）
        mid_box = BoxLayout(orientation="horizontal", spacing=6)
        self.map_widget = MapCanvasWidget(controller=self, size_hint_x=0.62)
        mid_box.add_widget(self.map_widget)

        right_panel = BoxLayout(orientation="vertical", size_hint_x=0.38, spacing=4)
        self.log_label = Label(
            text="",
            font_name=CJK_FONT,
            font_size="13sp",
            color=(0.88, 0.91, 0.96, 1),
            size_hint_y=None,
            halign="left",
            valign="top",
        )
        self.log_label.bind(
            width=lambda *_: setattr(self.log_label, "text_size", (self.log_label.width, None)),
            texture_size=lambda *_: setattr(self.log_label, "height", self.log_label.texture_size[1] + 12),
        )
        scroll = ScrollView( do_scroll_x=False )
        scroll.add_widget(self.log_label)
        right_panel.add_widget(scroll)
        mid_box.add_widget(right_panel)
        root.add_widget(mid_box)

        # 3. 底部手機觸控十字鍵與 Gemini 4 動態生成按鈕
        ctrl_bar = GridLayout(cols=6, size_hint_y=None, height=58, spacing=6)
        btns = [
            ("◀ 左移", (0.18, 0.24, 0.35, 1), lambda *_: self.move_player(-1, 0)),
            ("▲ 上移", (0.18, 0.24, 0.35, 1), lambda *_: self.move_player(0, -1)),
            ("▼ 下移", (0.18, 0.24, 0.35, 1), lambda *_: self.move_player(0, 1)),
            ("▶ 右移", (0.18, 0.24, 0.35, 1), lambda *_: self.move_player(1, 0)),
            ("💬 A 互動", (0.31, 0.27, 0.90, 1), lambda *_: self.interact_nearby()),
            ("✨ 生成下一章", (0.85, 0.47, 0.02, 1), lambda *_: self.trigger_gemini4_next_chapter()),
        ]
        for text, bg, cb in btns:
            b = Button(text=text, font_name=CJK_FONT, font_size="13sp", background_color=bg)
            b.bind(on_release=cb)
            ctrl_bar.add_widget(b)
        root.add_widget(ctrl_bar)

        self.logs = [
            "🌟 歡迎來到《星界迴響》Android 原生 App！",
            "👉 點擊地圖格子或下方方向鍵移動：藍圓=NPC、黃方=寶箱、紅圓=強敵、紫圈=前往下一章裂隙。",
        ]
        self._refresh_ui()
        return root

    def _get_key_file(self):
        try:
            return os.path.join(self.user_data_dir, "gemini_api_key.txt")
        except Exception:
            return "gemini_api_key.txt"

    def _load_saved_key(self):
        p = self._get_key_file()
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    self.api_key = f.read().strip()
            except Exception:
                pass

    def _build_grid(self, walls):
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

    def _init_chapter_1(self):
        self.map_grid = self._build_grid([[4, 2, 1], [4, 3, 1], [4, 6, 1], [8, 3, 2], [8, 4, 2], [8, 5, 2]])
        self.entities = [
            {
                "id": "npc_elaine",
                "type": "npc",
                "name": "守門人艾琳",
                "x": 4,
                "y": 4,
                "greeting": "「旅人，你的古舊星盤正在共鳴！啟動星門會抽乾村莊結界，你打算怎麼做？」",
                "choices": [
                    {
                        "label": "🛡️ 保護村莊：將星盤能量分給結界（共鳴-10，獲「守護紋章」）",
                        "effect": {"mana": -10, "trait": "仁慈守護者", "item": "守護紋章", "log": "選擇保護村莊結界，獲贈「守護紋章」。", "reply": "艾琳感激地行禮：「這枚紋章會在下個世界保護你！」"},
                    },
                    {
                        "label": "⚡ 強行超載星門：抽取結界能量（共鳴+25，獲「超載核心」）",
                        "effect": {"mana": 25, "trait": "狂熱求知者", "item": "超載核心", "log": "強行超載星門，取得「超載核心」。", "reply": "星門劇烈震動！艾琳驚呼：「小心裂隙裡的獵犬！」"},
                    },
                ],
            },
            {
                "id": "chest_1",
                "type": "chest",
                "name": "星塵寶箱",
                "x": 7,
                "y": 2,
                "greeting": "你在斷垣殘壁間發現一座古老的星塵寶箱。",
                "choices": [
                    {
                        "label": "🔓 用星盤共鳴解鎖（星幣+40，獲「記憶水晶」）",
                        "effect": {"gold": 40, "item": "記憶水晶", "log": "開啟星塵寶箱取得「記憶水晶」。", "reply": "寶箱彈開，獲得記錄上古秘辛的「記憶水晶」！"},
                    },
                    {
                        "label": "🔨 直接砸開寶箱（HP-10，星幣+65）",
                        "effect": {"hp": -10, "gold": 65, "trait": "果斷掠奪者", "log": "暴力砸開寶箱取得大量星幣。", "reply": "機關震傷了手，但你拿走了所有星幣！"},
                    },
                ],
            },
            {
                "id": "mob_1",
                "type": "monster",
                "name": "失控星界哨兵",
                "x": 10,
                "y": 6,
                "greeting": "失控星界哨兵擋在裂隙前：「警告—發現未授權生命體—」",
                "choices": [
                    {
                        "label": "⚔️ 正面揮劍擊破（HP-15，星幣+50，獲「哨兵核心」）",
                        "effect": {"hp": -15, "gold": 50, "item": "哨兵核心", "trait": "無畏戰士", "log": "正面擊破星界哨兵，奪取「哨兵核心」。", "reply": "你斬斷哨兵動力線，奪得「哨兵核心」！"},
                    },
                    {
                        "label": "🔧 用星盤改寫程式收服（共鳴-15，獲「機械夥伴」）",
                        "effect": {"mana": -15, "item": "機械夥伴", "trait": "機械親和者", "log": "改寫哨兵程式並收服為「機械夥伴」。", "reply": "哨兵紅光轉為藍光：「邏輯重設完成，聽候差遣。」"},
                    },
                ],
            },
            {
                "id": "portal_1",
                "type": "portal",
                "name": "時空裂隙",
                "x": 12,
                "y": 4,
            },
        ]

    def _add_log(self, msg: str):
        self.logs.append(msg)
        if len(self.logs) > 16:
            self.logs = self.logs[-16:]
        self._refresh_ui()

    def _refresh_ui(self):
        b_name = BIOMES.get(self.biome, BIOMES["ruins"])["name"]
        self.hud_label.text = (
            f"【第{self.chapter}章：{self.chapter_title} ({b_name})】 "
            f"HP:{self.hp} | 共鳴:{self.mana} | 星幣:{self.gold} | 傾向:{self.trait}"
        )
        inv_text = "🎒 背包：" + "、".join(self.inventory)
        self.log_label.text = inv_text + "\n\n" + "\n\n".join(self.logs)
        self.map_widget.redraw()

    def move_player(self, dx: int, dy: int):
        nx, ny = self.player_x + dx, self.player_y + dy
        if nx < 0 or nx >= MAP_COLS or ny < 0 or ny >= MAP_ROWS:
            return
        if self.map_grid[ny][nx] == 1:
            return
        for ent in self.entities:
            if ent["x"] == nx and ent["y"] == ny:
                self.open_entity_popup(ent)
                return
        self.player_x, self.player_y = nx, ny
        if self.map_grid[ny][nx] == 2:
            self.hp = max(1, self.hp - 2)
            self._add_log("⚠️ 踏入能量地形，HP -2")
        self._refresh_ui()

    def interact_nearby(self):
        for ent in self.entities:
            if abs(ent["x"] - self.player_x) + abs(ent["y"] - self.player_y) <= 1:
                self.open_entity_popup(ent)
                return
        self._add_log("💡 請先靠近地圖上的角色、寶箱或紫色裂隙再按互動。")

    def open_entity_popup(self, ent):
        if ent["type"] == "portal":
            self.trigger_gemini4_next_chapter()
            return

        box = BoxLayout(orientation="vertical", padding=10, spacing=8)
        greet = Label(
            text=ent.get("greeting", ""),
            font_name=CJK_FONT,
            font_size="14sp",
            halign="left",
            valign="top",
            size_hint_y=0.35,
        )
        greet.bind(size=greet.setter("text_size"))
        box.add_widget(greet)

        popup = Popup(
            title=f"💬 {ent['name']}",
            title_font=CJK_FONT,
            title_size="16sp",
            content=box,
            size_hint=(0.88, 0.78),
        )

        for ch in ent.get("choices", []):
            btn = Button(
                text=ch["label"],
                font_name=CJK_FONT,
                font_size="13sp",
                size_hint_y=None,
                height=48,
                background_color=(0.20, 0.25, 0.38, 1),
            )
            btn.bind(on_release=lambda _, c=ch: self._apply_choice(ent, c, popup))
            box.add_widget(btn)

        # 自訂行動輸入列
        custom_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=6)
        custom_in = TextInput(
            hint_text="或輸入你想做的自由行動...",
            font_name=CJK_FONT,
            font_size="13sp",
            multiline=False,
        )
        btn_custom = Button(
            text="自由行動",
            font_name=CJK_FONT,
            font_size="13sp",
            size_hint_x=None,
            width=95,
            background_color=(0.31, 0.27, 0.90, 1),
        )
        btn_custom.bind(
            on_release=lambda *_: self._apply_custom_action(ent, custom_in.text.strip(), popup)
        )
        custom_row.add_widget(custom_in)
        custom_row.add_widget(btn_custom)
        box.add_widget(custom_row)

        popup.open()

    def _apply_choice(self, ent, ch, popup):
        popup.dismiss()
        eff = ch.get("effect", {})
        self.hp = max(1, min(200, self.hp + int(eff.get("hp", 0))))
        self.mana = max(0, self.mana + int(eff.get("mana", 0)))
        self.gold = max(0, self.gold + int(eff.get("gold", 0)))
        if eff.get("trait"):
            self.trait = str(eff["trait"])
        if eff.get("item") and eff["item"] not in self.inventory:
            self.inventory.append(eff["item"])

        log_line = eff.get("log", f"對 {ent['name']} 選擇了：{ch['label']}")
        self.play_history.append(f"第{self.chapter}章：{log_line}")
        self._add_log(f"👉 {log_line}")
        if eff.get("reply"):
            self._add_log(f"💬 {eff['reply']}")

        if ent["type"] in ("chest", "monster"):
            self.entities = [e for e in self.entities if e["id"] != ent["id"]]
        self._refresh_ui()

    def _apply_custom_action(self, ent, act_text: str, popup):
        if not act_text:
            return
        popup.dismiss()
        self.mana += 10
        self.trait = "自由破局者"
        log_line = f"對「{ent['name']}」採取自由行動：「{act_text}」"
        self.play_history.append(f"第{self.chapter}章：{log_line}")
        self._add_log(f"⚡ {log_line}（已記錄為下一章劇情種子！）")

    def open_api_key_popup(self):
        box = BoxLayout(orientation="vertical", padding=10, spacing=8)
        info = Label(
            text="貼上 Google AI Studio 免費申請的 Gemini API Key，即可在手機連線 gemini-4-argon 即時生成新章節（不填寫也可使用內建動態劇本引擎）：",
            font_name=CJK_FONT,
            font_size="13sp",
            halign="left",
            valign="middle",
        )
        info.bind(size=info.setter("text_size"))
        key_input = TextInput(
            text=self.api_key,
            hint_text="AIzaSy...",
            font_name=CJK_FONT,
            multiline=False,
            size_hint_y=None,
            height=44,
        )
        btn_save = Button(
            text="儲存金鑰",
            font_name=CJK_FONT,
            size_hint_y=None,
            height=46,
            background_color=(0.06, 0.72, 0.50, 1),
        )
        popup = Popup(
            title="⚙️ 設定 Gemini 4 API Key",
            title_font=CJK_FONT,
            content=box,
            size_hint=(0.85, 0.55),
        )

        def _save(*_):
            self.api_key = key_input.text.strip()
            try:
                with open(self._get_key_file(), "w", encoding="utf-8") as f:
                    f.write(self.api_key)
            except Exception:
                pass
            popup.dismiss()
            self._add_log("✅ 已儲存 API Key 設定！")

        btn_save.bind(on_release=_save)
        box.add_widget(info)
        box.add_widget(key_input)
        box.add_widget(btn_save)
        popup.open()

    def tr
