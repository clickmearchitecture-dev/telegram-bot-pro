import sys
import os
import json
import threading
import time
import uuid
from datetime import datetime

import telebot
from telebot.types import (
    ReplyKeyboardMarkup, 
    KeyboardButton, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    WebAppInfo
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QPushButton, QTextEdit, QLabel, QLineEdit,
    QDialog, QFormLayout, QDialogButtonBox, QFileDialog,
    QComboBox, QTabWidget, QGridLayout, QToolButton,
    QListWidget, QListWidgetItem, QGroupBox, QSplitter,
    QMessageBox, QDateTimeEdit
)
from PyQt6.QtCore import pyqtSignal, QObject, Qt, QDateTime
from PyQt6.QtGui import QFont, QPixmap, QTextCursor

# =====================================================================
# ១. ការកំណត់ CONFIGURATION (SINGLE-PROFILE CUSTOMER VERSION)
# =====================================================================
CONFIG_FILE = "config.json"
DEFAULT_SHEET_NAME = "My_Customer_Orders"

DEFAULT_MENU_BUTTONS = {
    "វគ្គសិក្សា / សេវាកម្ម": {
        "reply_text": "សូមស្វាគមន៍មកកាន់សេវាកម្មរបស់យើង! សូមជ្រើសរើសជម្រើសខាងក្រោម៖",
        "image_path": "",
        "inlines": [{"text": "🌐 ចូលទៅកាន់ Channel", "url": "https://t.me/", "type": "url"}]
    }
}

SUB_MENU_LOOKUP = {}; MAIN_MENU_LOOKUP = {}; INLINE_LOOKUP = {}; SUB_INLINE_LOOKUP = {}
IMAGE_CACHE = {}

def generate_short_id(): return str(uuid.uuid4())[:8]

def load_config():
    data = {
        "BOT_TOKEN": "", 
        "SHEET_NAME": DEFAULT_SHEET_NAME, 
        "MENU_BUTTONS": json.loads(json.dumps(DEFAULT_MENU_BUTTONS)), 
        "SCHEDULED_TASKS": [], 
        "KNOWN_USERS": []
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                data.update(loaded)
        except: pass
    
    menu_data = data.get("MENU_BUTTONS", {})
    for main_key, main_val in menu_data.items():
        if 'id' not in main_val: main_val['id'] = generate_short_id()
        if 'image_path' not in main_val: main_val['image_path'] = ""
        for inl in main_val.get('inlines', []):
            if 'id' not in inl: inl['id'] = generate_short_id()
            if 'inline_reply_text' not in inl: inl['inline_reply_text'] = ""
            if 'inline_image_path' not in inl: inl['inline_image_path'] = ""
            if inl.get('type') == 'sub_menu':
                if 'sub_inlines' not in inl: inl['sub_inlines'] = []
                if 'sub_reply_text' not in inl: inl['sub_reply_text'] = "សូមជ្រើសរើសជម្រើសខាងក្រោម៖"
                if 'sub_image_path' not in inl: inl['sub_image_path'] = ""
                for sinl in inl.get('sub_inlines', []):
                    if 'id' not in sinl: sinl['id'] = generate_short_id()
                    if 'sub_inline_reply_text' not in sinl: sinl['sub_inline_reply_text'] = ""
                    if 'sub_inline_image_path' not in sinl: sinl['sub_inline_image_path'] = ""
    data["MENU_BUTTONS"] = menu_data
    rebuild_lookups(data["MENU_BUTTONS"])
    return data

def save_config_to_file():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(APP_CONFIG, f, indent=4, ensure_ascii=False)
    rebuild_lookups(APP_CONFIG["MENU_BUTTONS"])

def rebuild_lookups(menu_data):
    global SUB_MENU_LOOKUP, MAIN_MENU_LOOKUP, INLINE_LOOKUP, SUB_INLINE_LOOKUP
    SUB_MENU_LOOKUP.clear(); MAIN_MENU_LOOKUP.clear(); INLINE_LOOKUP.clear(); SUB_INLINE_LOOKUP.clear()
    for main_name, main_data in menu_data.items():
        MAIN_MENU_LOOKUP[main_data['id']] = {"name": main_name, "data": main_data}
        for inline in main_data.get("inlines", []):
            INLINE_LOOKUP[inline['id']] = {"parent_main_id": main_data['id'], "data": inline}
            if inline.get("type") == "sub_menu":
                SUB_MENU_LOOKUP[inline['id']] = {"parent_main_id": main_data['id'], "data": inline}
                for sinl in inline.get("sub_inlines", []):
                    SUB_INLINE_LOOKUP[sinl['id']] = {"parent_sub_id": inline['id'], "data": sinl}

APP_CONFIG = load_config()
QR_CODE_IMAGE_PATH = "qrcode.png"

# 🛠️ បញ្ឆោតកម្មវិធីកុំឱ្យគាំងពេលអត់មាន Token 
saved_token = APP_CONFIG.get("BOT_TOKEN", "")
safe_startup_token = saved_token if saved_token and ":" in saved_token else "1234567890:dummy_token_to_prevent_crash"
bot = telebot.TeleBot(safe_startup_token)

# =====================================================================
# ២. TELEGRAM BOT HANDLERS & CALLBACKS
# =====================================================================
def register_user(chat_id):
    c_id = str(chat_id)
    if c_id not in APP_CONFIG["KNOWN_USERS"]:
        APP_CONFIG["KNOWN_USERS"].append(c_id)
        save_config_to_file()

def send_menu_message(chat_id, reply_text, image_path, markup):
    try:
        safe_text = reply_text if reply_text else "សូមជ្រើសរើសជម្រើសខាងក្រោម៖"
        if image_path and os.path.exists(image_path):
            cache_key = f"{image_path}_{os.path.getmtime(image_path)}"
            if cache_key in IMAGE_CACHE:
                return bot.send_photo(chat_id, IMAGE_CACHE[cache_key], caption=safe_text, reply_markup=markup, parse_mode="Markdown")
            else:
                with open(image_path, 'rb') as f:
                    msg = bot.send_photo(chat_id, f, caption=safe_text, reply_markup=markup, parse_mode="Markdown")
                    IMAGE_CACHE[cache_key] = msg.photo[-1].file_id
                    return msg
        else:
            return bot.send_message(chat_id, safe_text, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        log_signal.log.emit(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Error: {str(e)}")

def build_inline_markup(inlines_list, parent_id_for_back=None, back_type="main"):
    markup = InlineKeyboardMarkup()
    for btn in inlines_list:
        text, btn_type, url = btn.get("text", "Link"), btn.get("type", "url"), btn.get("url", "").strip()
        if not url and btn_type in ["url", "miniapp"]: url = "https://t.me/"
        if not url and btn_type == "callback": url = "empty_callback"
        if btn_type in ["url", "miniapp"] and not url.startswith("http"): url = "https://" + url

        if btn_type == "miniapp": markup.add(InlineKeyboardButton(text, web_app=WebAppInfo(url=url)))
        elif btn_type == "callback": markup.add(InlineKeyboardButton(text, callback_data=url))
        elif btn_type == "sub_menu": markup.add(InlineKeyboardButton(text, callback_data=f"sub_{btn['id']}"))
        elif btn_type == "callback_msg": markup.add(InlineKeyboardButton(text, callback_data=f"msg_{btn['id']}"))
        elif btn_type == "callback_smsg": markup.add(InlineKeyboardButton(text, callback_data=f"smsg_{btn['id']}"))
        else: markup.add(InlineKeyboardButton(text, url=url))
            
    if parent_id_for_back:
        if back_type == "main": markup.add(InlineKeyboardButton("🔙 ត្រលប់ក្រោយ", callback_data=f"back_{parent_id_for_back}"))
        elif back_type == "sub": markup.add(InlineKeyboardButton("🔙 ត្រលប់ក្រោយ", callback_data=f"sub_{parent_id_for_back}"))
    return markup

@bot.message_handler(func=lambda message: message.text and message.text.lower() in ['/start', '/menu'])
def show_main_menu(message):
    register_user(message.chat.id)
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = list(APP_CONFIG["MENU_BUTTONS"].keys())
    for i in range(0, len(buttons), 2): markup.row(*[KeyboardButton(btn) for btn in buttons[i:i+2]])
    bot.send_message(message.chat.id, "🙏 សូមស្វាគមន៍មកកាន់ប្រព័ន្ធស្វ័យប្រវត្តិរបស់យើង!", reply_markup=markup)
    log_signal.update_user.emit(f"{message.from_user.id} | {message.from_user.first_name}")

@bot.message_handler(func=lambda message: message.text in APP_CONFIG["MENU_BUTTONS"])
def handle_dynamic_menu_buttons(message):
    register_user(message.chat.id)
    btn_data = APP_CONFIG["MENU_BUTTONS"][message.text]
    markup = build_inline_markup(btn_data.get("inlines", []))
    send_menu_message(message.chat.id, btn_data.get("reply_text", ""), btn_data.get("image_path", ""), markup)
    log_signal.update_user.emit(f"{message.from_user.id} | {message.from_user.first_name}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("sub_"))
def handle_sub_menu(call):
    register_user(call.message.chat.id)
    sub_id = call.data.replace("sub_", "")
    if sub_id not in SUB_MENU_LOOKUP: return bot.answer_callback_query(call.id, "⚠️ មិនមានទិន្នន័យទេ!")
    sub_info = SUB_MENU_LOOKUP[sub_id]
    markup = build_inline_markup(sub_info["data"].get("sub_inlines", []), parent_id_for_back=sub_info["parent_main_id"], back_type="main")
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass
    send_menu_message(call.message.chat.id, sub_info["data"].get("sub_reply_text", ""), sub_info["data"].get("sub_image_path", ""), markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("msg_"))
def handle_inline_msg(call):
    register_user(call.message.chat.id)
    msg_id = call.data.replace("msg_", "")
    if msg_id not in INLINE_LOOKUP: return bot.answer_callback_query(call.id, "⚠️ មិនមានទិន្នន័យទេ!")
    inl_data = INLINE_LOOKUP[msg_id]["data"]
    markup = build_inline_markup([], parent_id_for_back=INLINE_LOOKUP[msg_id]["parent_main_id"], back_type="main")
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass
    send_menu_message(call.message.chat.id, inl_data.get("inline_reply_text", ""), inl_data.get("inline_image_path", ""), markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("smsg_"))
def handle_sub_inline_msg(call):
    register_user(call.message.chat.id)
    msg_id = call.data.replace("smsg_", "")
    if msg_id not in SUB_INLINE_LOOKUP: return bot.answer_callback_query(call.id, "⚠️ មិនមានទិន្នន័យទេ!")
    sinl_data = SUB_INLINE_LOOKUP[msg_id]["data"]
    markup = build_inline_markup([], parent_id_for_back=SUB_INLINE_LOOKUP[msg_id]["parent_sub_id"], back_type="sub")
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass
    send_menu_message(call.message.chat.id, sinl_data.get("sub_inline_reply_text", ""), sinl_data.get("sub_inline_image_path", ""), markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("back_"))
def handle_back_main(call):
    register_user(call.message.chat.id)
    main_id = call.data.replace("back_", "")
    if main_id not in MAIN_MENU_LOOKUP: return bot.answer_callback_query(call.id, "⚠️ មិនមានទិន្នន័យទេ!")
    main_data = MAIN_MENU_LOOKUP[main_id]["data"]
    markup = build_inline_markup(main_data.get("inlines", []))
    try: bot.delete_message(call.message.chat.id, call.message.message_id)
    except: pass
    send_menu_message(call.message.chat.id, main_data.get("reply_text", ""), main_data.get("image_path", ""), markup)
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_user_custom_message(message):
    register_user(message.chat.id)
    bot.reply_to(message, "🙏 អរគុណសម្រាប់សាររបស់អ្នក! Admin នឹងតបទៅវិញឆាប់ៗ។")
    log_signal.update_user.emit(f"{message.from_user.id} | {message.from_user.first_name}")
    log_signal.log.emit(f"[{datetime.now().strftime('%H:%M:%S')}] 💬 សារពី {message.from_user.first_name}: {message.text}")

class LogSignal(QObject):
    log = pyqtSignal(str); update_user = pyqtSignal(str); broadcast_log = pyqtSignal(str); refresh_schedule_ui = pyqtSignal()
log_signal = LogSignal()

# =====================================================================
# ៣. ផ្ទាំង EMOJI PICKER
# =====================================================================
class EmojiPickerDialog(QDialog):
    def __init__(self, parent=None, on_emoji_selected=None):
        super().__init__(parent); self.on_emoji_selected = on_emoji_selected; self.setWindowTitle("😊 ជ្រើសរើសរូបអារម្មណ៍"); self.setFixedSize(380, 320)
        self.setStyleSheet("""QDialog { background-color: #181825; color: #cdd6f4; border: 1px solid #45475a; border-radius: 8px; } QTabWidget::pane { border: 1px solid #313244; background-color: #11111b; border-radius: 6px; } QTabBar::tab { background: #181825; color: #a6adc8; padding: 8px 12px; border-top-left-radius: 6px; border-top-right-radius: 6px; font-size: 13px; } QTabBar::tab:selected { background: #313244; color: #89b4fa; font-weight: bold; } QToolButton { background-color: transparent; border-radius: 4px; font-size: 18px; padding: 4px; } QToolButton:hover { background-color: #313244; }""")
        layout = QVBoxLayout(self); layout.setContentsMargins(8, 8, 8, 8); tab_widget = QTabWidget()
        emoji_categories = {"😊 អារម្មណ៍": ["😊", "😂", "😍", "🥰", "😘", "😁", "😆", "😅", "😋", "😎", "🤩", "🥳", "😭", "😢", "🥺", "😱", "😡", "🤬", "🤫", "🤔"], "👍 កាយវិការ": ["🙏", "👍", "👎", "👌", "✌️", "🤞", "🤝", "👏", "🙌", "👐", "🤲", "💪", "👆", "👇", "👈", "👉", "✍️", "💅", "🙋‍♂️", "🙋‍♀️"], "💼 ទំនិញ": ["💼", "📦", "🛒", "🎁", "💡", "📞", "📱", "💻", "🖥️", "🖨️", "⏰", "⏳", "📅", "📊", "📈", "📉", "💰", "💵", "💎", "💳"], "🌟 សញ្ញា": ["❤️", "🧡", "💛", "💚", "💙", "💜", "🖤", "🤍", "💔", "💖", "💯", "🔥", "⭐", "🌟", "✨", "⚡", "✅", "❌", "⚠️", "📌"]}
        for tab_name, emojis in emoji_categories.items():
            tab_page = QWidget(); grid = QGridLayout(tab_page); grid.setSpacing(4); grid.setContentsMargins(6, 6, 6, 6); row, col = 0, 0
            for emo in emojis:
                btn = QToolButton(); btn.setText(emo); btn.setFixedSize(40, 40); btn.clicked.connect(lambda _, e=emo: self.select_emoji(e)); grid.addWidget(btn, row, col)
                col += 1
                if col >= 7: col = 0; row += 1
            tab_widget.addTab(tab_page, tab_name)
        layout.addWidget(tab_widget)
    def select_emoji(self, emo):
        if self.on_emoji_selected: self.on_emoji_selected(emo)
        self.accept()

# =====================================================================
# ៤. ផ្ទាំង ADMIN PANEL 
# =====================================================================
class AdminPanelDialog(QDialog):
    def __init__(self, current_menu_data, parent=None):
        super().__init__(parent); self.setWindowTitle("🛠️ Admin Panel"); self.resize(1200, 750)
        self.setStyleSheet("""QDialog { background-color: #181825; color: #ffffff; font-family: 'Khmer OS Battambang'; } QGroupBox { border: 1px solid #45475a; border-radius: 6px; margin-top: 15px; font-weight: bold; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; } QLabel { color: #ffffff; } QListWidget { background-color: #11111b; border: 1px solid #313244; border-radius: 6px; color: #cdd6f4; padding: 5px; } QLineEdit, QComboBox, QTextEdit { background-color: #11111b; border: 1px solid #45475a; border-radius: 4px; padding: 5px; color: #a6adc8; } QPushButton { border-radius: 4px; padding: 6px; font-weight: bold; }""")
        self.menu_data = json.loads(json.dumps(current_menu_data))
        self.current_main_img = ""; self.current_in_img = ""; self.current_sub_img = ""; self.current_sin_img = ""
        self.init_ui(); self.refresh_main_buttons()

    def create_input_with_emoji(self, widget):
        lay = QHBoxLayout(); lay.setContentsMargins(0, 0, 0, 0); lay.addWidget(widget)
        btn = QPushButton("😊"); btn.setFixedSize(30, 30); btn.setStyleSheet("background-color: #313244; color: #ffffff; border-radius: 4px; border: 1px solid #45475a;")
        btn.clicked.connect(lambda checked, w=widget: EmojiPickerDialog(self, lambda e: self.insert_emoji(w, e)).exec())
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignTop)
        c = QWidget(); c.setLayout(lay); return c
        
    def insert_emoji(self, widget, emo):
        if isinstance(widget, QLineEdit): widget.insert(emo)
        elif isinstance(widget, QTextEdit): widget.textCursor().insertText(emo)
        widget.setFocus()

    def init_ui(self):
        layout = QVBoxLayout(self); splitter = QSplitter(Qt.Orientation.Horizontal)
        
        col1 = QGroupBox("១. គ្រប់គ្រងប៊ូតុងធំៗ"); lay1 = QVBoxLayout(col1)
        self.main_btn_list = QListWidget(); self.main_btn_list.currentItemChanged.connect(self.on_main_selected); lay1.addWidget(self.main_btn_list)
        
        sort_lay1 = QHBoxLayout()
        btn_up1 = QPushButton("🔼"); btn_up1.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 2px;"); btn_up1.clicked.connect(self.move_main_up)
        btn_down1 = QPushButton("🔽"); btn_down1.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 2px;"); btn_down1.clicked.connect(self.move_main_down)
        sort_lay1.addWidget(QLabel("ផ្លាស់ប្តូរទីតាំង៖")); sort_lay1.addWidget(btn_up1); sort_lay1.addWidget(btn_down1); sort_lay1.addStretch()
        lay1.addLayout(sort_lay1)
        
        self.input_main_name = QLineEdit(); lay1.addWidget(QLabel("ឈ្មោះប៊ូតុងធំ៖")); lay1.addWidget(self.create_input_with_emoji(self.input_main_name))
        self.input_main_reply = QTextEdit(); self.input_main_reply.setFixedHeight(55); lay1.addWidget(QLabel("សារឆ្លើយតប៖")); lay1.addWidget(self.create_input_with_emoji(self.input_main_reply))
        img1_lay = QHBoxLayout(); self.lbl_main_img = QLabel("គ្មានរូប"); self.lbl_main_img.setFixedSize(40, 40); self.lbl_main_img.setStyleSheet("border: 1px dashed #6c7086;")
        btn_img1 = QPushButton("🖼️ រូបភាព"); btn_img1.clicked.connect(lambda: self.select_img("main"))
        btn_clr1 = QPushButton("❌"); btn_clr1.clicked.connect(lambda: self.clear_img("main"))
        img1_lay.addWidget(self.lbl_main_img); img1_lay.addWidget(btn_img1); img1_lay.addWidget(btn_clr1); lay1.addLayout(img1_lay)
        acts1 = QHBoxLayout()
        btn_add1 = QPushButton("➕ បង្កើតថ្មី"); btn_add1.setStyleSheet("background-color: #a6e3a1; color: #11111b;"); btn_add1.clicked.connect(self.add_main)
        btn_edit1 = QPushButton("✏️ កែប្រែ"); btn_edit1.setStyleSheet("background-color: #f9e2af; color: #11111b;"); btn_edit1.clicked.connect(self.edit_main)
        btn_del1 = QPushButton("🗑️ លុប"); btn_del1.setStyleSheet("background-color: #eba0ac; color: #11111b;"); btn_del1.clicked.connect(self.del_main)
        acts1.addWidget(btn_add1); acts1.addWidget(btn_edit1); acts1.addWidget(btn_del1); lay1.addLayout(acts1); splitter.addWidget(col1)

        col2 = QGroupBox("២. គ្រប់គ្រង Inline"); lay2 = QVBoxLayout(col2)
        self.inline_list = QListWidget(); self.inline_list.currentItemChanged.connect(self.on_inline_selected); lay2.addWidget(self.inline_list)
        
        sort_lay2 = QHBoxLayout()
        btn_up2 = QPushButton("🔼"); btn_up2.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 2px;"); btn_up2.clicked.connect(self.move_inline_up)
        btn_down2 = QPushButton("🔽"); btn_down2.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 2px;"); btn_down2.clicked.connect(self.move_inline_down)
        sort_lay2.addWidget(QLabel("ផ្លាស់ប្តូរទីតាំង៖")); sort_lay2.addWidget(btn_up2); sort_lay2.addWidget(btn_down2); sort_lay2.addStretch()
        lay2.addLayout(sort_lay2)

        self.input_in_name = QLineEdit(); lay2.addWidget(QLabel("ឈ្មោះ Inline៖")); lay2.addWidget(self.create_input_with_emoji(self.input_in_name))
        self.combo_in_type = QComboBox(); self.combo_in_type.addItems(["🌐 Link", "📱 Mini App", "💳 QR Code", "📂 Sub-Menu", "✉️ សារ+រូប"]); lay2.addWidget(QLabel("ប្រភេទ៖")); lay2.addWidget(self.combo_in_type)
        self.input_in_url = QLineEdit(); lay2.addWidget(QLabel("URL/Link៖")); lay2.addWidget(self.create_input_with_emoji(self.input_in_url))
        self.input_in_reply = QTextEdit(); self.input_in_reply.setFixedHeight(55); lay2.addWidget(QLabel("សារអត្ថបទ៖")); lay2.addWidget(self.create_input_with_emoji(self.input_in_reply))
        
        img2_lay = QHBoxLayout(); self.lbl_in_img = QLabel("គ្មានរូប"); self.lbl_in_img.setFixedSize(40, 40); self.lbl_in_img.setStyleSheet("border: 1px dashed #6c7086;")
        btn_img2 = QPushButton("🖼️ រូបភាព"); btn_img2.clicked.connect(lambda: self.select_img("in"))
        btn_clr2 = QPushButton("❌"); btn_clr2.clicked.connect(lambda: self.clear_img("in"))
        img2_lay.addWidget(self.lbl_in_img); img2_lay.addWidget(btn_img2); img2_lay.addWidget(btn_clr2); lay2.addLayout(img2_lay)
        
        acts2 = QHBoxLayout()
        btn_add2 = QPushButton("➕ បង្កើត Inline"); btn_add2.setStyleSheet("background-color: #89dceb; color: #11111b;"); btn_add2.clicked.connect(self.add_inline)
        btn_edit2 = QPushButton("✏️ កែប្រែ"); btn_edit2.setStyleSheet("background-color: #f9e2af; color: #11111b;"); btn_edit2.clicked.connect(self.edit_inline)
        btn_del2 = QPushButton("🗑️ លុប"); btn_del2.setStyleSheet("background-color: #f38ba8; color: #11111b;"); btn_del2.clicked.connect(self.del_inline)
        acts2.addWidget(btn_add2); acts2.addWidget(btn_edit2); acts2.addWidget(btn_del2); lay2.addLayout(acts2); splitter.addWidget(col2)

        self.col3 = QGroupBox("៣. គ្រប់គ្រង Sub-Menu"); self.col3.setEnabled(False); lay3 = QVBoxLayout(self.col3)
        self.input_sub_reply = QTextEdit(); self.input_sub_reply.setFixedHeight(45); lay3.addWidget(QLabel("👉 សារស្វាគមន៍ Sub-Menu៖")); lay3.addWidget(self.create_input_with_emoji(self.input_sub_reply))
        img3_lay = QHBoxLayout(); self.lbl_sub_img = QLabel("គ្មានរូប"); self.lbl_sub_img.setFixedSize(40, 40); self.lbl_sub_img.setStyleSheet("border: 1px dashed #6c7086;")
        btn_img3 = QPushButton("🖼️ រូបភាព"); btn_img3.clicked.connect(lambda: self.select_img("sub"))
        btn_clr3 = QPushButton("❌"); btn_clr3.clicked.connect(lambda: self.clear_img("sub"))
        img3_lay.addWidget(self.lbl_sub_img); img3_lay.addWidget(btn_img3); img3_lay.addWidget(btn_clr3); lay3.addLayout(img3_lay)
        btn_save_sub = QPushButton("💾 Update សារ & រូបភាព"); btn_save_sub.setStyleSheet("background-color: #cba6f7; color: #11111b;"); btn_save_sub.clicked.connect(self.save_sub_header); lay3.addWidget(btn_save_sub)
        
        self.sub_list = QListWidget(); self.sub_list.currentItemChanged.connect(self.on_sub_selected); lay3.addWidget(QLabel("👇 បញ្ជី Sub-Inline៖")); lay3.addWidget(self.sub_list)
        
        sort_lay3 = QHBoxLayout()
        btn_up3 = QPushButton("🔼"); btn_up3.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 2px;"); btn_up3.clicked.connect(self.move_sub_up)
        btn_down3 = QPushButton("🔽"); btn_down3.setStyleSheet("background-color: #313244; color: #cdd6f4; padding: 2px;"); btn_down3.clicked.connect(self.move_sub_down)
        sort_lay3.addWidget(QLabel("ផ្លាស់ប្តូរទីតាំង៖")); sort_lay3.addWidget(btn_up3); sort_lay3.addWidget(btn_down3); sort_lay3.addStretch()
        lay3.addLayout(sort_lay3)

        self.input_sin_name = QLineEdit(); lay3.addWidget(QLabel("ឈ្មោះ Sub-Inline៖")); lay3.addWidget(self.create_input_with_emoji(self.input_sin_name))
        self.combo_sin_type = QComboBox(); self.combo_sin_type.addItems(["🌐 Link", "📱 Mini App", "💳 QR Code", "✉️ សារ+រូប"]); lay3.addWidget(QLabel("ប្រភេទ៖")); lay3.addWidget(self.combo_sin_type)
        self.input_sin_url = QLineEdit(); lay3.addWidget(QLabel("URL/Link៖")); lay3.addWidget(self.create_input_with_emoji(self.input_sin_url))
        self.input_sin_reply = QTextEdit(); self.input_sin_reply.setFixedHeight(45); lay3.addWidget(QLabel("សារអត្ថបទ៖")); lay3.addWidget(self.create_input_with_emoji(self.input_sin_reply))
        img4_lay = QHBoxLayout(); self.lbl_sin_img = QLabel("គ្មានរូប"); self.lbl_sin_img.setFixedSize(40, 40); self.lbl_sin_img.setStyleSheet("border: 1px dashed #6c7086;")
        btn_img4 = QPushButton("🖼️ រូបភាព"); btn_img4.clicked.connect(lambda: self.select_img("sin"))
        btn_clr4 = QPushButton("❌"); btn_clr4.clicked.connect(lambda: self.clear_img("sin"))
        img4_lay.addWidget(self.lbl_sin_img); img4_lay.addWidget(btn_img4); img4_lay.addWidget(btn_clr4); lay3.addLayout(img4_lay)
        
        acts3 = QHBoxLayout()
        btn_add3 = QPushButton("➕ បង្កើត Sub"); btn_add3.setStyleSheet("background-color: #a6e3a1; color: #11111b;"); btn_add3.clicked.connect(self.add_sub)
        btn_edit3 = QPushButton("✏️ កែប្រែ"); btn_edit3.setStyleSheet("background-color: #f9e2af; color: #11111b;"); btn_edit3.clicked.connect(self.edit_sub)
        btn_del3 = QPushButton("🗑️ លុប"); btn_del3.setStyleSheet("background-color: #eba0ac; color: #11111b;"); btn_del3.clicked.connect(self.del_sub)
        acts3.addWidget(btn_add3); acts3.addWidget(btn_edit3); acts3.addWidget(btn_del3); lay3.addLayout(acts3); splitter.addWidget(self.col3); layout.addWidget(splitter)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); btns.setStyleSheet("QPushButton { background-color: #89b4fa; color: #11111b; padding: 8px 20px; font-weight: bold; }")
        layout.addWidget(btns)

    def move_main_up(self):
        row = self.main_btn_list.currentRow()
        if row > 0:
            items = list(self.menu_data.items()); items[row - 1], items[row] = items[row], items[row - 1]
            self.menu_data = dict(items); self.refresh_main_buttons(); self.main_btn_list.setCurrentRow(row - 1)
    def move_main_down(self):
        row = self.main_btn_list.currentRow()
        if row >= 0 and row < len(self.menu_data) - 1:
            items = list(self.menu_data.items()); items[row + 1], items[row] = items[row], items[row + 1]
            self.menu_data = dict(items); self.refresh_main_buttons(); self.main_btn_list.setCurrentRow(row + 1)
    def move_inline_up(self):
        m_it = self.main_btn_list.currentItem(); row = self.inline_list.currentRow()
        if m_it and row > 0:
            lst = self.menu_data[m_it.text()]["inlines"]; lst[row - 1], lst[row] = lst[row], lst[row - 1]
            self.refresh_inline_buttons(m_it.text()); self.inline_list.setCurrentRow(row - 1)
    def move_inline_down(self):
        m_it = self.main_btn_list.currentItem(); row = self.inline_list.currentRow()
        if m_it and row >= 0:
            lst = self.menu_data[m_it.text()]["inlines"]
            if row < len(lst) - 1:
                lst[row + 1], lst[row] = lst[row], lst[row + 1]; self.refresh_inline_buttons(m_it.text()); self.inline_list.setCurrentRow(row + 1)
    def move_sub_up(self):
        m_it, i_it = self.main_btn_list.currentItem(), self.inline_list.currentItem(); row = self.sub_list.currentRow()
        if m_it and i_it and row > 0:
            lst = self.menu_data[m_it.text()]["inlines"][self.inline_list.currentRow()]["sub_inlines"]; lst[row - 1], lst[row] = lst[row], lst[row - 1]
            self.refresh_sub_inlines(self.menu_data[m_it.text()]["inlines"][self.inline_list.currentRow()]); self.sub_list.setCurrentRow(row - 1)
    def move_sub_down(self):
        m_it, i_it = self.main_btn_list.currentItem(), self.inline_list.currentItem(); row = self.sub_list.currentRow()
        if m_it and i_it and row >= 0:
            lst = self.menu_data[m_it.text()]["inlines"][self.inline_list.currentRow()]["sub_inlines"]
            if row < len(lst) - 1:
                lst[row + 1], lst[row] = lst[row], lst[row + 1]; self.refresh_sub_inlines(self.menu_data[m_it.text()]["inlines"][self.inline_list.currentRow()]); self.sub_list.setCurrentRow(row + 1)

    def select_img(self, target):
        path, _ = QFileDialog.getOpenFileName(self, "ជ្រើសរើសរូប", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if path:
            px = QPixmap(path).scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            if target == "main": self.current_main_img = path; self.lbl_main_img.setPixmap(px)
            elif target == "in": self.current_in_img = path; self.lbl_in_img.setPixmap(px)
            elif target == "sub": self.current_sub_img = path; self.lbl_sub_img.setPixmap(px)
            elif target == "sin": self.current_sin_img = path; self.lbl_sin_img.setPixmap(px)
    def clear_img(self, target):
        if target == "main": self.current_main_img = ""; self.lbl_main_img.setText("គ្មានរូប")
        elif target == "in": self.current_in_img = ""; self.lbl_in_img.setText("គ្មានរូប")
        elif target == "sub": self.current_sub_img = ""; self.lbl_sub_img.setText("គ្មានរូប")
        elif target == "sin": self.current_sin_img = ""; self.lbl_sin_img.setText("គ្មានរូប")

    def refresh_main_buttons(self):
        self.main_btn_list.clear()
        for btn_name in self.menu_data.keys(): self.main_btn_list.addItem(btn_name)

    def on_main_selected(self, item):
        if not item: return
        btn_data = self.menu_data.get(item.text(), {})
        self.input_main_name.setText(item.text()); self.input_main_reply.setPlainText(btn_data.get("reply_text", ""))
        self.current_main_img = btn_data.get("image_path", ""); self.clear_img("main") if not self.current_main_img else self.select_img_path("main", self.current_main_img)
        self.refresh_inline_buttons(item.text())

    def select_img_path(self, target, path):
        if os.path.exists(path):
            px = QPixmap(path).scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            if target == "main": self.lbl_main_img.setPixmap(px)
            elif target == "in": self.lbl_in_img.setPixmap(px)
            elif target == "sub": self.lbl_sub_img.setPixmap(px)
            elif target == "sin": self.lbl_sin_img.setPixmap(px)

    def add_main(self):
        if not self.input_main_name.text().strip(): return
        self.menu_data[self.input_main_name.text().strip()] = {"id": generate_short_id(), "reply_text": self.input_main_reply.toPlainText().strip(), "image_path": self.current_main_img, "inlines": []}
        self.refresh_main_buttons()

    def edit_main(self):
        if not self.main_btn_list.currentItem() or not self.input_main_name.text().strip(): return
        old, new = self.main_btn_list.currentItem().text(), self.input_main_name.text().strip()
        new_data = {}
        for k, v in self.menu_data.items():
            if k == old: new_data[new] = {"id": v.get("id", generate_short_id()), "reply_text": self.input_main_reply.toPlainText().strip(), "image_path": self.current_main_img, "inlines": v.get("inlines", [])}
            else: new_data[k] = v
        self.menu_data = new_data; self.refresh_main_buttons()

    def del_main(self):
        if self.main_btn_list.currentItem(): del self.menu_data[self.main_btn_list.currentItem().text()]; self.refresh_main_buttons()

    def refresh_inline_buttons(self, main_name):
        self.inline_list.clear(); self.col3.setEnabled(False)
        for inline in self.menu_data.get(main_name, {}).get("inlines", []):
            it = QListWidgetItem(f"🌐 {inline['text']}"); it.setData(Qt.ItemDataRole.UserRole, inline); self.inline_list.addItem(it)

    def on_inline_selected(self, item):
        if not item: return
        data = item.data(Qt.ItemDataRole.UserRole)
        self.input_in_name.setText(data.get("text", "")); self.input_in_url.setText(data.get("url", "")); self.input_in_reply.setPlainText(data.get("inline_reply_text", ""))
        self.current_in_img = data.get("inline_image_path", ""); self.clear_img("in") if not self.current_in_img else self.select_img_path("in", self.current_in_img)
        t = data.get("type", "url"); idx = 0 if t=="url" else 1 if t=="miniapp" else 2 if t=="callback" else 3 if t=="sub_menu" else 4; self.combo_in_type.setCurrentIndex(idx)
        if t == "sub_menu":
            self.col3.setEnabled(True); self.input_sub_reply.setPlainText(data.get("sub_reply_text", ""))
            self.current_sub_img = data.get("sub_image_path", ""); self.clear_img("sub") if not self.current_sub_img else self.select_img_path("sub", self.current_sub_img)
            self.refresh_sub_inlines(data)
        else: self.col3.setEnabled(False)

    def get_type(self, c_box):
        idx = c_box.currentIndex()
        if c_box == self.combo_in_type: return "url" if idx==0 else "miniapp" if idx==1 else "callback" if idx==2 else "sub_menu" if idx==3 else "callback_msg"
        return "url" if idx==0 else "miniapp" if idx==1 else "callback" if idx==2 else "callback_smsg"

    def add_inline(self):
        if not self.main_btn_list.currentItem(): return
        t = self.get_type(self.combo_in_type)
        new_in = {"id": generate_short_id(), "text": self.input_in_name.text().strip(), "url": self.input_in_url.text().strip(), "type": t, "inline_reply_text": self.input_in_reply.toPlainText().strip(), "inline_image_path": self.current_in_img}
        if t == "sub_menu": new_in.update({"sub_inlines": [], "sub_reply_text": "ជ្រើសរើសខាងក្រោម៖", "sub_image_path": ""})
        self.menu_data[self.main_btn_list.currentItem().text()]["inlines"].append(new_in); self.refresh_inline_buttons(self.main_btn_list.currentItem().text())

    def edit_inline(self):
        if not self.main_btn_list.currentItem() or not self.inline_list.currentItem(): return
        m, idx, t = self.main_btn_list.currentItem().text(), self.inline_list.currentRow(), self.get_type(self.combo_in_type)
        old_data = self.menu_data[m]["inlines"][idx]
        new_in = {"id": old_data.get("id", generate_short_id()), "text": self.input_in_name.text().strip(), "url": self.input_in_url.text().strip(), "type": t, "inline_reply_text": self.input_in_reply.toPlainText().strip(), "inline_image_path": self.current_in_img}
        if t == "sub_menu": new_in.update({"sub_inlines": old_data.get("sub_inlines", []), "sub_reply_text": old_data.get("sub_reply_text", "ជ្រើសរើសខាងក្រោម៖"), "sub_image_path": old_data.get("sub_image_path", "")})
        self.menu_data[m]["inlines"][idx] = new_in; self.refresh_inline_buttons(m)

    def del_inline(self):
        if self.main_btn_list.currentItem() and self.inline_list.currentItem():
            del self.menu_data[self.main_btn_list.currentItem().text()]["inlines"][self.inline_list.currentRow()]; self.refresh_inline_buttons(self.main_btn_list.currentItem().text())

    def save_sub_header(self):
        if not self.main_btn_list.currentItem() or not self.inline_list.currentItem(): return
        data = self.menu_data[self.main_btn_list.currentItem().text()]["inlines"][self.inline_list.currentRow()]
        data["sub_reply_text"] = self.input_sub_reply.toPlainText().strip(); data["sub_image_path"] = self.current_sub_img
        QMessageBox.information(self, "ជោគជ័យ", "បានរក្សាទុករូបភាព និងសារសម្រាប់ Sub-Menu នេះ!")

    def refresh_sub_inlines(self, inline_data):
        self.sub_list.clear()
        for sin in inline_data.get("sub_inlines", []):
            it = QListWidgetItem(f"🌐 {sin['text']}"); it.setData(Qt.ItemDataRole.UserRole, sin); self.sub_list.addItem(it)

    def on_sub_selected(self, item):
        if not item: return
        data = item.data(Qt.ItemDataRole.UserRole)
        self.input_sin_name.setText(data.get("text", "")); self.input_sin_url.setText(data.get("url", "")); self.input_sin_reply.setPlainText(data.get("sub_inline_reply_text", ""))
        self.current_sin_img = data.get("sub_inline_image_path", ""); self.clear_img("sin") if not self.current_sin_img else self.select_img_path("sin", self.current_sin_img)
        t = data.get("type", "url"); idx = 0 if t=="url" else 1 if t=="miniapp" else 2 if t=="callback" else 3; self.combo_sin_type.setCurrentIndex(idx)

    def add_sub(self):
        if not self.main_btn_list.currentItem() or not self.inline_list.currentItem(): return
        m, idx = self.main_btn_list.currentItem().text(), self.inline_list.currentRow()
        new_sub = {"id": generate_short_id(), "text": self.input_sin_name.text().strip(), "url": self.input_sin_url.text().strip(), "type": self.get_type(self.combo_sin_type), "sub_inline_reply_text": self.input_sin_reply.toPlainText().strip(), "sub_inline_image_path": self.current_sin_img}
        self.menu_data[m]["inlines"][idx]["sub_inlines"].append(new_sub); self.refresh_sub_inlines(self.menu_data[m]["inlines"][idx])

    def edit_sub(self):
        if not self.main_btn_list.currentItem() or not self.inline_list.currentItem() or not self.sub_list.currentItem(): return
        m, idx_in, idx_sub = self.main_btn_list.currentItem().text(), self.inline_list.currentRow(), self.sub_list.currentRow()
        old_id = self.menu_data[m]["inlines"][idx_in]["sub_inlines"][idx_sub].get("id", generate_short_id())
        self.menu_data[m]["inlines"][idx_in]["sub_inlines"][idx_sub] = {"id": old_id, "text": self.input_sin_name.text().strip(), "url": self.input_sin_url.text().strip(), "type": self.get_type(self.combo_sin_type), "sub_inline_reply_text": self.input_sin_reply.toPlainText().strip(), "sub_inline_image_path": self.current_sin_img}
        self.refresh_sub_inlines(self.menu_data[m]["inlines"][idx_in])

    def del_sub(self):
        if self.main_btn_list.currentItem() and self.inline_list.currentItem() and self.sub_list.currentItem():
            del self.menu_data[self.main_btn_list.currentItem().text()]["inlines"][self.inline_list.currentRow()]["sub_inlines"][self.sub_list.currentRow()]
            self.refresh_sub_inlines(self.menu_data[self.main_btn_list.currentItem().text()]["inlines"][self.inline_list.currentRow()])
    def get_updated_menu(self): return self.menu_data

# =====================================================================
# ៥. MAIN WINDOW (SINGLE PROFILE)
# =====================================================================
class BotMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.bot_thread = None; self.schedule_thread = None; self.is_running = False
        self.selected_image_path = None; self.broadcast_img_path = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("ប្រព័ន្ធគ្រប់គ្រង Telegram Bot & Marketing (Customer Version)")
        self.resize(1000, 800)
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e2e; color: #ffffff; font-family: 'Khmer OS Battambang'; }
            QLabel { color: #ffffff; }
            QTabWidget::pane { border: 1px solid #45475a; background-color: #181825; border-radius: 8px; }
            QTabBar::tab { background: #1e1e2e; color: #a6adc8; padding: 10px 20px; font-weight: bold; border-top-left-radius: 8px; border-top-right-radius: 8px; margin-right: 2px;}
            QTabBar::tab:selected { background: #181825; color: #89b4fa; border-top: 3px solid #89b4fa; }
            QLineEdit, QComboBox, QTextEdit, QDateTimeEdit { background-color: #11111b; border: 1px solid #45475a; border-radius: 4px; padding: 5px; color: #ffffff; }
            QPushButton { border-radius: 4px; padding: 8px; font-weight: bold; }
            QListWidget { background-color: #11111b; border: 1px solid #45475a; border-radius: 6px; padding: 5px; color: #f9e2af; }
        """)
        
        self.main_tab_widget = QTabWidget(); self.setCentralWidget(self.main_tab_widget)
        self.main_tab_widget.addTab(self.init_telegram_bot_tab(), "🤖 Telegram Bot Pro")
        self.main_tab_widget.addTab(self.init_marketing_tab(), "📣 Marketing Automation")
        self.main_tab_widget.addTab(QWidget(), "📁 Files ឯកសារ (ឆាប់ៗនេះ)")
        
        log_signal.log.connect(self.append_log)
        log_signal.update_user.connect(self.set_active_user_id)
        log_signal.broadcast_log.connect(self.append_broadcast_log)
        log_signal.refresh_schedule_ui.connect(self.refresh_schedule_list)
        
        self.refresh_known_users_combo()

    def refresh_known_users_combo(self):
        self.target_user_id.clear()
        for u in APP_CONFIG.get("KNOWN_USERS", []): self.set_active_user_id(f"{u} | អតិថិជនចាស់")

    # ======== Tab 1: Bot Pro ======== 
    def init_telegram_bot_tab(self):
        tab1 = QWidget(); main_layout = QVBoxLayout(tab1)
        settings_layout = QVBoxLayout()
        
        # 📌 ប្រអប់ Token ធម្មតា ដូចរូបភាពទី១៥ 
        token_layout = QHBoxLayout()
        self.token_input = QLineEdit()
        # បង្ហាញ Token បើមាន បើអត់មានគឺប្រអប់ទទេស្អាត
        self.token_input.setText(APP_CONFIG.get("BOT_TOKEN", ""))
        token_layout.addWidget(QLabel("🔑 Bot Token:")); token_layout.addWidget(self.token_input); settings_layout.addLayout(token_layout)

        sheet_layout = QHBoxLayout()
        self.sheet_input = QLineEdit()
        self.sheet_input.setText(APP_CONFIG.get("SHEET_NAME", DEFAULT_SHEET_NAME))
        sheet_layout.addWidget(QLabel("📊 Sheet Name:")); sheet_layout.addWidget(self.sheet_input); settings_layout.addLayout(sheet_layout)

        action_layout = QHBoxLayout()
        self.btn_open_admin = QPushButton("🛠️ ផ្ទាំង Admin Panel"); self.btn_open_admin.setStyleSheet("background-color: #f9e2af; color: #11111b;")
        self.btn_open_admin.clicked.connect(self.open_admin_panel); action_layout.addWidget(self.btn_open_admin); action_layout.addStretch()
        self.btn_save_config = QPushButton("💾 Save រក្សាទុកការកំណត់"); self.btn_save_config.setStyleSheet("background-color: #a6e3a1; color: #11111b;")
        self.btn_save_config.clicked.connect(self.save_config_action); action_layout.addWidget(self.btn_save_config); settings_layout.addLayout(action_layout)
        main_layout.addLayout(settings_layout)

        reply_box_layout = QHBoxLayout()
        self.target_user_id = QComboBox(); self.target_user_id.setEditable(True); self.target_user_id.setFixedWidth(200); reply_box_layout.addWidget(self.target_user_id)
        self.admin_msg_input = QLineEdit(); reply_box_layout.addWidget(self.admin_msg_input)
        self.btn_send_msg = QPushButton("📤 ផ្ញើសារ"); self.btn_send_msg.setStyleSheet("background-color: #89dceb; color: #11111b;")
        self.btn_send_msg.clicked.connect(self.send_admin_message); reply_box_layout.addWidget(self.btn_send_msg); main_layout.addLayout(reply_box_layout)

        extra_tools_layout = QHBoxLayout()
        self.btn_upload_image = QPushButton("📎 ជ្រើសឯកសារ/រូប"); self.btn_upload_image.setStyleSheet("background-color: #cba6f7; color: #11111b;")
        self.btn_upload_image.clicked.connect(self.select_file_attachment); extra_tools_layout.addWidget(self.btn_upload_image)
        self.btn_clear_image = QPushButton("❌"); self.btn_clear_image.setEnabled(False); self.btn_clear_image.clicked.connect(self.clear_image)
        extra_tools_layout.addWidget(self.btn_clear_image)
        self.image_preview_label = QLabel(); self.image_preview_label.setFixedSize(36, 36); extra_tools_layout.addWidget(self.image_preview_label); extra_tools_layout.addStretch()
        main_layout.addLayout(extra_tools_layout)

        self.log_display = QTextEdit(); self.log_display.setReadOnly(True); main_layout.addWidget(self.log_display)

        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ ចាប់ផ្តើម Bot (Start)"); self.btn_start.setStyleSheet("background-color: #89b4fa; color: #11111b; font-size: 14px; padding: 12px;")
        self.btn_start.clicked.connect(self.start_bot); btn_layout.addWidget(self.btn_start)
        self.btn_stop = QPushButton("◼ បញ្ឈប់ Bot (Stop)"); self.btn_stop.setEnabled(False); self.btn_stop.setStyleSheet("background-color: #f38ba8; color: #11111b; font-size: 14px; padding: 12px;")
        self.btn_stop.clicked.connect(self.stop_bot); btn_layout.addWidget(self.btn_stop); main_layout.addLayout(btn_layout)
        return tab1

    # ======== Tab 2: Marketing ======== 
    def init_marketing_tab(self):
        tab = QWidget(); lay = QVBoxLayout(tab); lay.setSpacing(15)
        
        compose_box = QGroupBox("១. រៀបចំសារប្រូម៉ូសិន (Composer)"); compose_box.setStyleSheet("QGroupBox { border: 1px solid #45475a; border-radius: 6px; margin-top: 10px; font-weight: bold; color: #f9e2af; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        c_lay = QVBoxLayout(compose_box)
        self.bc_msg_input = QTextEdit(); self.bc_msg_input.setFixedHeight(80); c_lay.addWidget(self.bc_msg_input)
        
        tool_lay = QHBoxLayout()
        btn_emoji_bc = QPushButton("😊 Emoji"); btn_emoji_bc.setStyleSheet("background-color: #313244; color: #ffffff;")
        btn_emoji_bc.clicked.connect(lambda: EmojiPickerDialog(self, lambda e: self.bc_msg_input.textCursor().insertText(e)).exec())
        tool_lay.addWidget(btn_emoji_bc)
        
        self.lbl_bc_img = QLabel("គ្មានរូប"); self.lbl_bc_img.setFixedSize(36, 36); self.lbl_bc_img.setStyleSheet("border: 1px dashed #6c7086;")
        btn_img_bc = QPushButton("🖼️ រូបភាព"); btn_img_bc.setStyleSheet("background-color: #cba6f7; color: #11111b;"); btn_img_bc.clicked.connect(self.select_bc_img)
        btn_clr_bc = QPushButton("❌"); btn_clr_bc.setStyleSheet("background-color: #eba0ac; color: #11111b;"); btn_clr_bc.clicked.connect(self.clear_bc_img)
        tool_lay.addWidget(self.lbl_bc_img); tool_lay.addWidget(btn_img_bc); tool_lay.addWidget(btn_clr_bc); tool_lay.addStretch()
        c_lay.addLayout(tool_lay)
        
        sched_lay = QHBoxLayout()
        sched_lay.addWidget(QLabel("📅 ថ្ងៃម៉ោងផ្ញើ៖"))
        self.time_picker = QDateTimeEdit(QDateTime.currentDateTime()); self.time_picker.setCalendarPopup(True); sched_lay.addWidget(self.time_picker)
        sched_lay.addWidget(QLabel("🔄 ប្រភេទ៖"))
        self.combo_freq = QComboBox(); self.combo_freq.addItems(["ផ្ញើតែម្តង (One-Time)", "វិលជុំរៀងរាល់ថ្ងៃ (Daily Recurring)"]); sched_lay.addWidget(self.combo_freq)
        
        btn_add_queue = QPushButton("⏳ បន្ថែមចូលបញ្ជីរង់ចាំ (Add to Queue)"); btn_add_queue.setStyleSheet("background-color: #a6e3a1; color: #11111b;")
        btn_add_queue.clicked.connect(self.add_to_schedule_queue); sched_lay.addWidget(btn_add_queue); sched_lay.addStretch()
        c_lay.addLayout(sched_lay); lay.addWidget(compose_box)

        queue_box = QGroupBox("២. បញ្ជីគ្រប់គ្រងសាររង់ចាំ (Scheduled Task Manager)"); queue_box.setStyleSheet("QGroupBox { border: 1px solid #45475a; border-radius: 6px; margin-top: 10px; font-weight: bold; color: #89dceb; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }")
        q_lay = QVBoxLayout(queue_box)
        self.schedule_list = QListWidget(); q_lay.addWidget(self.schedule_list)
        btn_del_queue = QPushButton("🗑️ លុបការកំណត់ដែលបានជ្រើសរើស (Cancel Task)"); btn_del_queue.setStyleSheet("background-color: #eba0ac; color: #11111b;")
        btn_del_queue.clicked.connect(self.delete_scheduled_task); q_lay.addWidget(btn_del_queue, alignment=Qt.AlignmentFlag.AlignRight)
        lay.addWidget(queue_box)

        lay.addWidget(QLabel("📊 ប្រវត្តិដំណើរការ Broadcast៖"))
        self.bc_log = QTextEdit(); self.bc_log.setReadOnly(True); self.bc_log.setFixedHeight(120); lay.addWidget(self.bc_log)
        
        self.refresh_schedule_list()
        return tab

    # ======== Marketing Tab Functions ========
    def select_bc_img(self):
        path, _ = QFileDialog.getOpenFileName(self, "ជ្រើសរើសរូប", "", "Images (*.png *.jpg *.jpeg *.webp)")
        if path: self.broadcast_img_path = path; self.lbl_bc_img.setPixmap(QPixmap(path).scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
    def clear_bc_img(self): self.broadcast_img_path = None; self.lbl_bc_img.clear(); self.lbl_bc_img.setText("គ្មានរូប")
    def append_broadcast_log(self, text): self.bc_log.append(text)

    def add_to_schedule_queue(self):
        msg_text = self.bc_msg_input.toPlainText().strip()
        if not msg_text and not self.broadcast_img_path:
            QMessageBox.warning(self, "ព្រមាន", "សូមវាយបញ្ចូលសារ ឬដាក់រូបភាពជាមុនសិន!")
            return
            
        target_time = self.time_picker.dateTime().toSecsSinceEpoch()
        freq = "daily" if self.combo_freq.currentIndex() == 1 else "one_time"
        
        if target_time <= time.time():
            reply = QMessageBox.question(self, "បញ្ជាក់ការផ្ញើ", "ម៉ោងនេះគឺបច្ចុប្បន្ន។ តើអ្នកចង់បាញ់សារនេះ ឥឡូវនេះតែម្តងឬ?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.append_broadcast_log(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 ចាប់ផ្តើមផ្ញើសារបន្ទាន់...")
                threading.Thread(target=self.run_broadcast_thread, args=(msg_text, self.broadcast_img_path, APP_CONFIG.get("KNOWN_USERS", [])), daemon=True).start()
                self.bc_msg_input.clear(); self.clear_bc_img()
            return

        task = {
            "id": generate_short_id(), "text": msg_text, "image_path": self.broadcast_img_path,
            "target_time": target_time, "frequency": freq, "created_at": time.time()
        }
        APP_CONFIG.setdefault("SCHEDULED_TASKS", []).append(task)
        save_config_to_file(); self.refresh_schedule_list()
        self.bc_msg_input.clear(); self.clear_bc_img()
        self.append_broadcast_log(f"[{datetime.now().strftime('%H:%M:%S')}] ⏳ បានបន្ថែមចូលបញ្ជីរង់ចាំដោយជោគជ័យ!")

    def refresh_schedule_list(self):
        self.schedule_list.clear()
        for t in APP_CONFIG.get("SCHEDULED_TASKS", []):
            dt_str = datetime.fromtimestamp(t["target_time"]).strftime('%Y-%m-%d %I:%M %p')
            freq_str = "🔁 រាល់ថ្ងៃ" if t.get("frequency") == "daily" else "▶️ តែម្តង"
            img_str = "🖼️ រូបភាព +" if t.get("image_path") else ""
            txt_preview = t["text"][:30] + "..." if len(t["text"]) > 30 else t["text"]
            
            label = f"[{dt_str}] | {freq_str} | {img_str} 📝 '{txt_preview}'"
            it = QListWidgetItem(label); it.setData(Qt.ItemDataRole.UserRole, t["id"]); self.schedule_list.addItem(it)

    def delete_scheduled_task(self):
        item = self.schedule_list.currentItem()
        if not item: return
        t_id = item.data(Qt.ItemDataRole.UserRole)
        APP_CONFIG["SCHEDULED_TASKS"] = [t for t in APP_CONFIG.get("SCHEDULED_TASKS", []) if t["id"] != t_id]
        save_config_to_file(); self.refresh_schedule_list()
        self.append_broadcast_log(f"[{datetime.now().strftime('%H:%M:%S')}] 🗑️ បានលុបការកំណត់ចេញពីបញ្ជី!")

    def run_broadcast_thread(self, text, img_path, target_ids):
        if not target_ids:
            log_signal.broadcast_log.emit(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ មិនមានអតិថិជនសម្រាប់ផ្ញើទេ!")
            return
            
        success_count = 0; fail_count = 0
        log_signal.broadcast_log.emit(f"[{datetime.now().strftime('%H:%M:%S')}] ⚡ កំពុងបាញ់សារទៅមនុស្ស {len(target_ids)} នាក់...")
        
        for chat_id in target_ids:
            try:
                if img_path and os.path.exists(img_path):
                    with open(img_path, 'rb') as f: bot.send_photo(chat_id, f, caption=text, parse_mode="Markdown")
                else: bot.send_message(chat_id, text, parse_mode="Markdown")
                success_count += 1
            except: fail_count += 1
            time.sleep(0.5) 
            
        log_signal.broadcast_log.emit(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ ប្រតិបត្តិការរួចរាល់! ជោគជ័យ: {success_count} នាក់ | បរាជ័យ: {fail_count} នាក់។")

    def run_schedule_checker(self):
        while self.is_running:
            now = time.time(); tasks_to_run = []
            for t in list(APP_CONFIG.get("SCHEDULED_TASKS", [])):
                if now >= t["target_time"]: tasks_to_run.append(t)
            
            if tasks_to_run:
                for t in tasks_to_run:
                    threading.Thread(target=self.run_broadcast_thread, args=(t["text"], t.get("image_path"), APP_CONFIG.get("KNOWN_USERS", [])), daemon=True).start()
                    if t.get("frequency") == "daily": t["target_time"] += 86400 
                    else: APP_CONFIG["SCHEDULED_TASKS"].remove(t)
                save_config_to_file(); log_signal.refresh_schedule_ui.emit()
            time.sleep(10) 

    # ======== Tab 1 General Methods ========
    def append_log(self, text): self.log_display.append(text)
    def set_active_user_id(self, user_info_str):
        if self.target_user_id.findText(user_info_str) == -1: self.target_user_id.insertItem(0, user_info_str)
        self.target_user_id.setCurrentText(user_info_str)
    def select_file_attachment(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "ជ្រើសរើសឯកសារ", "", "All Files (*.*)")
        if file_path: self.selected_image_path = file_path; self.image_preview_label.setText("📄"); self.btn_clear_image.setEnabled(True)
    def clear_image(self): self.selected_image_path = None; self.image_preview_label.clear(); self.btn_clear_image.setEnabled(False)

    def send_admin_message(self):
        if not self.is_running: return
        target_id = self.target_user_id.currentText().split(" | ")[0].strip()
        msg = self.admin_msg_input.text().strip()
        if not target_id or (not msg and not self.selected_image_path): return
        try:
            if self.selected_image_path:
                with open(self.selected_image_path, "rb") as f: bot.send_document(target_id, f, caption=f"💬 Admin: {msg}")
            else: bot.send_message(target_id, f"💬 Admin: {msg}")
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] 📤 បានផ្ញើទៅ {target_id}!")
            self.admin_msg_input.clear(); self.clear_image()
        except Exception as e: self.append_log(f"Error: {e}")

    def open_admin_panel(self):
        dialog = AdminPanelDialog(APP_CONFIG.get("MENU_BUTTONS", {}), self)
        if dialog.exec():
            APP_CONFIG["MENU_BUTTONS"] = dialog.get_updated_menu()
            save_config_to_file()
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] 🛠️ បាន Save រចនាសម្ព័ន្ធប៊ូតុងថ្មី!")

    def save_config_action(self):
        token = self.token_input.text().strip()
        sheet = self.sheet_input.text().strip()
        if token and sheet:
            APP_CONFIG["BOT_TOKEN"] = token
            APP_CONFIG["SHEET_NAME"] = sheet
            bot.token = token
            save_config_to_file()
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] 💾 បាន Save ការកំណត់ចូលក្នុងប្រព័ន្ធរលូន!")

    def start_bot(self):
        # ឆែកមើលក្រែងលោអតិថិជនមិនទាន់វាយបញ្ចូល Token ឬវាយខុស
        input_token = self.token_input.text().strip()
        if not input_token or ":" not in input_token:
            QMessageBox.warning(self, "ព្រមាន", "សូមវាយបញ្ចូល Bot Token ឱ្យបានត្រឹមត្រូវជាមុនសិន!")
            return
            
        if not self.is_running:
            bot.token = input_token
            self.is_running = True; self.btn_start.setEnabled(False); self.btn_stop.setEnabled(True)
            self.btn_open_admin.setEnabled(False); self.btn_save_config.setEnabled(False)
            self.token_input.setEnabled(False)
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Bot ដំណើរការ និងប្រព័ន្ធឆ្លាតវៃ (Scheduler) ត្រូវបានបើក...")
            self.bot_thread = threading.Thread(target=self.run_bot_polling, daemon=True); self.bot_thread.start()
            self.schedule_thread = threading.Thread(target=self.run_schedule_checker, daemon=True); self.schedule_thread.start()

    def run_bot_polling(self):
        while self.is_running:
            try: bot.polling(none_stop=True)
            except: time.sleep(3)

    def stop_bot(self):
        if self.is_running:
            self.is_running = False; bot.stop_polling()
            self.btn_start.setEnabled(True); self.btn_stop.setEnabled(False)
            self.btn_open_admin.setEnabled(True); self.btn_save_config.setEnabled(True)
            self.token_input.setEnabled(True)
            self.append_log(f"[{datetime.now().strftime('%H:%M:%S')}] 🛑 Bot បានបញ្ឈប់!")

if __name__ == "__main__":
    app = QApplication(sys.argv); window = BotMainWindow(); window.show(); sys.exit(app.exec())