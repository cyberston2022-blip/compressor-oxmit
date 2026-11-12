"""
Oxmit Dynamic Inline Buttons and Navigation Keyboards.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_profile_keyboard(user_tier: str = "normal", selected_profile: str = None) -> InlineKeyboardMarkup:
    profiles = [
        ("⚡ TgCompat (Fast)", "tgcompat"),
        ("⚖️ Balanced", "balanced"),
        ("🦁 Rostam (Extreme)", "rostam"),
        ("🎓 Edu360 (HEVC)", "edu360_hevc"),
        ("🎓 Edu480 (HEVC)", "edu480_hevc"),
    ]
    if user_tier == "vip":
        profiles.append(("💎 HighQ 1080p", "r1080"))

    buttons = []
    for label, code in profiles:
        prefix = "✅ " if selected_profile == code else ""
        buttons.append([InlineKeyboardButton(text=f"{prefix}{label}", callback_data=f"prof:{code}")])
    
    # Navigation row
    buttons.append([
        InlineKeyboardButton(text="◀️ Back", callback_data="nav:home"),
        InlineKeyboardButton(text="⚙️ Settings", callback_data="nav:settings")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_nav_bar(back_callback: str = "nav:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Back", callback_data=back_callback),
        InlineKeyboardButton(text="🏠 Main Menu", callback_data="nav:home")
    ]])

def get_merge_builder_kb(clip_count: int) -> InlineKeyboardMarkup:
    kb = []
    if clip_count >= 2:
        kb.append([InlineKeyboardButton(text=f"🎬 Merge ({clip_count} clips)", callback_data="merge:execute")])
    kb.append([
        InlineKeyboardButton(text="➕ Add Clip", callback_data="merge:add"),
        InlineKeyboardButton(text="🗑 Clear", callback_data="merge:reset")
    ])
    kb.append([InlineKeyboardButton(text="❌ Cancel", callback_data="nav:home")])
    return InlineKeyboardMarkup(inline_keyboard=kb)
