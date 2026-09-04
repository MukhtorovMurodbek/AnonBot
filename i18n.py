"""Translation strings for AnonBot's end-user-facing text (English, Uzbek,
Russian). Deliberately duplicated per bot -- same "no shared files between
bots" independence as shared_features.py -- but the STRINGS content here is
specific to this bot's own commands and flows.

Admin-only output (/dbdump, /status) is intentionally NOT translated -- see
build_status_text/error_summary/detect_host_environment in
shared_features.py, and bot.py's dbdump_command/status_command, left as
plain English since only the bot owner reads them.

The keys below split into two groups:
  - "Shared" keys (donate flow, sibling-bot blurb) exist under the exact
    same names in every bot's i18n.py, since shared_features.py is
    duplicated byte-identical across the family and calls t() with these
    names regardless of which bot it's running in.
  - Bot-specific keys, everything below the shared block, for this bot's
    own bot.py strings only.
"""
import asyncio

import db

SUPPORTED_LANGUAGES = ("en", "uz", "ru")
LANGUAGE_LABELS = {"en": "English 🇬🇧", "uz": "O'zbekcha 🇺🇿", "ru": "Русский 🇷🇺"}

# What every /start shows, whether or not the user already has a language.
# Deliberately not part of STRINGS: it is trilingual on purpose, so there
# is no single `lang` to look it up under.
LANGUAGE_PROMPT = (
    "👋 Welcome! / Xush kelibsiz! / Добро пожаловать!\n\n"
    "Please choose your language / Iltimos, tilni tanlang / "
    "Пожалуйста, выберите язык:"
)

STRINGS = {
    "en": {
        "flood_wait": "You're going faster than I can keep up with -- give it about {seconds} second(s) and carry on.",
        # ---- shared keys (same name in every bot's i18n.py) ----
        "sibling_blurb": "Also part of this bot family, see below \U0001f447",
        "donation_nudge": (
            "💙 If this bot's been useful: hosting/API costs are covered by whoever's "
            "running it, and /donate is a totally optional way to help keep it alive. "
            "No pressure either way!"
        ),
        "donate_unknown_currency": 'Unknown currency "{currency}" -- try xtr or usd.',
        "donate_currency_not_configured": "{currency} donations aren't set up on this bot yet -- try Stars instead.",
        "donate_invalid_amount": "That's not a valid amount -- try e.g. /donate 500 or /donate 5 usd.",
        "donate_prompt": (
            "Thank you for contributing -- it goes directly toward this bot's "
            "hosting and API costs. Choose an amount below, or Custom to enter "
            "your own (you can also send /donate <number> [usd] directly)."
        ),
        "donate_custom_button": "✏️ Custom {symbol}",
        "donate_too_many_stars": "That's a lot of stars! Keep it under {max} ⭐ per donation.",
        "donate_out_of_range": "{currency} donations need to be between {lo} and {hi} {symbol}.",
        "donate_invoice_title": "Buy the bot a coffee ☕",
        "donate_invoice_description": "A one-time voluntary donation towards hosting costs. Thank you!",
        "donate_invoice_label": "Donation",
        "donate_invoice_error": "⚠️ Telegram wouldn't create that invoice: {error}",
        "stars_unit": "Stars",
        "donate_custom_ask": "How many {unit} would you like to donate? Reply with a number.",
        "donate_invalid_amount_retry": "That's not a valid amount -- send /donate to try again.",
        "donate_thanks": "🙏 Thank you for the {amount} ⭐ — genuinely appreciated!",
        "language_set_confirmation": "✅ Language set to English.",
        "cancel_header": "\u274c Cancelled:",
        "cancel_nothing": "Nothing to cancel -- I wasn't waiting on anything from you.",
        "cancel_ask": "What should I stop? Here's what I'm waiting on:",
        "cancel_kept": "Alright -- nothing cancelled.",
        "cancel_reply_box_freed": "Your reply box is free again.",
        "cancel_button_all": "❌ All of it",
        "cancel_button_none": "↩️ Nothing, keep going",
        "cancel_button_donation": "💸 Donation amount",
        "cancel_item_donation": "the donation amount I asked you for",
        "cancel_item_stale_prompt": "a leftover prompt that was still waiting on an answer",
        "cancel_item_anon_session": "the anonymous chat you had open -- tap the link again to start a new one",
        "cancel_button_anon_session": "💬 The anonymous chat you're in",
        "cancel_item_reply_prompt": "the reply you were writing",
        "cancel_button_reply_prompt": "↩️ The reply you were writing",
        # ---- anon_bot-specific keys ----
        "start_greeting": "Hey! This bot runs anonymous-question inboxes.\n\n",
        "help_text": (
            "Two ways to use this bot:\n\n"
            "Get your own inbox -- /link gives you a permanent link. Post it "
            "anywhere public (bio, channel, story, wherever). Anyone who taps it "
            "can send you an anonymous message right here in this chat -- you "
            "won't see who they are.\n"
            "Answer by replying to the message -- swipe it, or tap the Reply "
            "button under it. That is how I know which conversation your "
            "answer belongs to, so it is required rather than optional: one "
            "public link means several people can be mid-conversation with "
            "you at once, and a message that doesn't say which thread it "
            "answers could reach the wrong one. Your answer shows up on their "
            "end as a real reply too.\n\n"
            "Got sent someone else's link? Tap it and write -- your first "
            "message goes straight through, with your identity hidden. After "
            "that, reply to the message you're answering, exactly as the "
            "other side does. Tapping the same link again later starts a "
            "brand-new conversation, it won't continue the old one.\n\n"
            "Commands:\n"
            "/link - get your inbox link\n"
            "/newlink - reset it (invalidates the old one)\n"
            "/pause, /resume - stop/allow new conversations\n"
            "/blocked - review who you've blocked\n"
            "/stats - quick counts for your inbox\n"
            "/donate - chip in for hosting costs (totally optional)\n"
            "/cancel - stop something I'm waiting on you for (I'll ask which)\n"
            "/en, /uz, /rus - switch language (or /language, which asks)\n\n"
        ),
        "follow_link_invalid": "That link isn't valid -- it may have been reset by whoever shared it. Ask them for a fresh one.",
        "follow_link_own": "That's your own inbox link -- messaging yourself would just be a note to self! Share it with other people instead: /link",
        "follow_link_blocked": "You're not able to message this person.",
        "follow_link_paused": "This person isn't accepting new anonymous messages right now -- try again later.",
        "follow_link_started": (
            "You're messaging someone anonymously (conversation #{conv_number}) -- "
            "they'll see your message but not who you are"
            "\n\nJust type your first message below. After that, reply to "
            "the message you're answering -- swipe it, or tap the Reply "
            "button under it -- so your words always land in the right "
            "conversation.\n\nTapping this link again later starts a "
            "brand-new conversation, separate from this one -- and this one "
            "keeps working: reply to any message in it whenever you like."
        ),
        "link_status_paused": "paused -- not accepting new conversations",
        "link_status_active": "accepting messages",
        "link_message": (
            "Your anonymous-inbox link ({status}):\n"
            "<code>{url}</code>\n\n"
            "Tap it to copy, then post it anywhere -- anyone who opens it can message "
            "you here without you seeing who they are."
        ),
        "link_button_pause": "⏸️ Pause",
        "link_button_resume": "▶️ Resume",
        "link_button_newlink": "🔄 New link",
        "anonlink_no_link_yet": "No link yet -- send /link first.",
        "anonlink_paused_answer": "Paused.",
        "anonlink_resumed_answer": "Resumed.",
        "anonlink_newlink_answer": "New link generated -- the old one no longer starts new conversations.",
        "newlink_message": "New link (the old one no longer starts new conversations):\n<code>{url}</code>",
        "pause_message": (
            "Paused -- your link won't start new conversations until /resume. Conversations "
            "already in progress still work normally."
        ),
        "resume_message": "Resumed -- your link is accepting new conversations again.",
        "stats_message": "{followers} distinct guest(s) have messaged you, across {conversations} conversation(s) total.",
        "blocked_none": "You haven't blocked anyone.",
        "blocked_header": "Blocked guests:",
        "blocked_guest_line": "  \U0001f6ab Guest from conversation(s) {conversations}",
        "blocked_guest_line_unknown": "  \U0001f6ab Guest (no conversation on record)",
        "blocked_unblock_button": "↩️ Unblock (conv. {conversations})",
        "blocked_unblock_button_unknown": "↩️ Unblock",
        "reply_button": "↩️ Reply",
        "block_button": "\U0001f6ab Block",
        "reply_prompt": "✍️ Replying in conversation #{conv_number}, to:\n{quote}",
        "reply_placeholder": "Your reply...",
        "opening_placeholder": "Your message...",
        "not_your_conversation": "Not your conversation.",
        "blocked_answer": "Blocked.",
        "unblock_button_labelled": "↩️ Unblock conversation #{conv_number}",
        "too_fast": "You're sending those faster than I can pass them on -- give it about {seconds} second(s) and try again.",
        "edit_not_relayed": (
            "I'd already passed that message on, so the edit didn't reach them -- they "
            "still have what you first wrote. Reply to it again with the correction."
        ),
        "unblocked_answer": "Unblocked.",
        "delivery_blocked": "Your message couldn't be delivered.",
        "inbox_gone": "This inbox no longer exists.",
        "incoming_header": "\U0001f4e9 Conversation #{conv_number}",
        "incoming_header_follower": "\U0001f4ec Conversation #{conv_number}",
        "delivery_forbidden": (
            "Couldn't deliver that -- this bot can't message someone who hasn't started "
            "it themselves, and this person hasn't yet. Nothing was sent."
        ),
        "delivery_failed": "Couldn't deliver that message: {error}",
        "sent_confirmation": "Sent ✅",
        "reply_no_match": "Couldn't match that reply to a conversation.",
        "must_reply": (
            "Reply to the message you're answering -- swipe it, or tap "
            "\u21a9\ufe0f Reply under it -- so I know which conversation this "
            "belongs to.\n\nOr send it as it is with the button below."
        ),
        "must_reply_button": "Send it anyway",
        "must_reply_ambiguous": (
            "Reply to the message you're answering -- swipe it, or tap "
            "\u21a9\ufe0f Reply under it.\n\nSeveral conversations are open "
            "in this chat, so a message that doesn't say which one it answers "
            "could reach the wrong person. Nothing was sent."
        ),
        "must_reply_expired": "That message is no longer waiting to be sent -- send it again.",
        "update_soon_try_later": "🔧 I'm being updated in a moment, so I can't start anything new right now — please try again in about {minutes} minute(s). I'll message you when I'm back.",
        "update_soon_try_later_soon": "🔧 I'm being updated right now, so I can't start anything new — please try again shortly. I'll message you when I'm back.",
        "update_will_reset": "🔧 Heads up: I'm about to be updated, and what you have going right now will be reset. You'll be able to start it again in a few minutes.",
        "update_done_try_now": '✅ The update is done — go ahead and try again now.',
        "reply_forbidden": "Couldn't deliver your reply -- they may have blocked or left the bot.",
        "reply_failed": "Couldn't deliver your reply: {error}",
        "delivered_confirmation": "Delivered ↩️",
        "reply_stale": (
            "I don't have that message on record, so I can't tell which conversation "
            "this answers. Reply to one of the messages I delivered here instead -- "
            "swipe it, or tap ↩️ Reply under it. Nothing was sent."
        ),
        "generic_nudge": "Not sure what this is for -- if someone sent you a link, tap that first. Want your own inbox? Send /link.",
        "unknown_command": "I don't recognize that command. Send /help to see what I can do.",
    },
    "uz": {
        "flood_wait": "Siz men ulgurganimdan tezroq yuboryapsiz -- taxminan {seconds} soniya kutib, davom eting.",
        "sibling_blurb": "Bu bot oilasining bir qismi, pastda ko'ring \U0001f447",
        "donation_nudge": (
            "💙 Agar bu bot foydali bo'lgan bo'lsa: hosting/API xarajatlarini uni ishga "
            "tushirgan kishi qoplaydi, /donate esa uni tirik saqlashga yordam berishning "
            "ixtiyoriy usuli. Bosim yo'q, xohlasangiz ham, xohlamasangiz ham!"
        ),
        "donate_unknown_currency": '"{currency}" — noma\'lum valyuta. xtr yoki usd dan foydalaning.',
        "donate_currency_not_configured": "{currency} orqali xayriya bu botda hali sozlanmagan — Stars dan foydalaning.",
        "donate_invalid_amount": "Bu noto'g'ri miqdor — masalan, /donate 500 yoki /donate 5 usd deb yozing.",
        "donate_prompt": (
            "Hissa qo'shganingiz uchun rahmat — bu mablag' to'g'ridan-to'g'ri "
            "botning hosting va API xarajatlariga sarflanadi. Quyidan miqdorni "
            "tanlang yoki o'zingiz kiritish uchun \"Boshqa\"ni bosing (shuningdek, "
            "to'g'ridan-to'g'ri /donate <son> [usd] deb yuborishingiz mumkin)."
        ),
        "donate_custom_button": "✏️ Boshqa {symbol}",
        "donate_too_many_stars": "Bu juda ko'p yulduzcha! Har bir xayriya {max} ⭐ dan kam bo'lsin.",
        "donate_out_of_range": "{currency} xayriyalar {lo} va {hi} {symbol} oralig'ida bo'lishi kerak.",
        "donate_invoice_title": "Botga bir chashka qahva sotib oling ☕",
        "donate_invoice_description": "Hosting xarajatlariga bir martalik ixtiyoriy xayriya. Rahmat!",
        "donate_invoice_label": "Xayriya",
        "donate_invoice_error": "⚠️ Telegram bu hisob-fakturani yarata olmadi: {error}",
        "stars_unit": "Stars (yulduzcha)",
        "donate_custom_ask": "Nechta {unit} xayriya qilmoqchisiz? Raqam bilan javob bering.",
        "donate_invalid_amount_retry": "Bu noto'g'ri miqdor — qayta urinish uchun /donate yuboring.",
        "donate_thanks": "🙏 {amount} ⭐ uchun rahmat — bu chindan ham qadrlanadi!",
        "language_set_confirmation": "✅ Til o'zbekchaga o'zgartirildi.",
        "cancel_header": "\u274c Bekor qilindi:",
        "cancel_nothing": "Bekor qiladigan narsa yo'q -- men sizdan hech narsa kutmayotgan edim.",
        "cancel_ask": "Nimani to'xtatay? Mana, men nimalarni kutyapman:",
        "cancel_kept": "Yaxshi -- hech narsa bekor qilinmadi.",
        "cancel_reply_box_freed": "Javob yozish oynasi yana bo'sh.",
        "cancel_button_all": "❌ Hammasini",
        "cancel_button_none": "↩️ Hech narsani, davom etamiz",
        "cancel_button_donation": "💸 Xayriya miqdori",
        "cancel_item_donation": "men so'ragan xayriya miqdori",
        "cancel_item_stale_prompt": "javob kutib qolgan eski so'rov",
        "cancel_item_anon_session": "ochiq turgan anonim suhbat -- yangisini boshlash uchun havolani qayta bosing",
        "cancel_button_anon_session": "💬 Siz turgan anonim suhbat",
        "cancel_item_reply_prompt": "siz yozayotgan javob",
        "cancel_button_reply_prompt": "↩️ Siz yozayotgan javob",
        "start_greeting": "Salom! Bu bot anonim savol-javob qutilarini boshqaradi.\n\n",
        "help_text": (
            "Bu botdan foydalanishning ikki usuli bor:\n\n"
            "O'zingizning qutingizni oling -- /link sizga doimiy havola beradi. "
            "Uni istalgan ochiq joyga joylashtiring (bio, kanal, hikoya, qayer bo'lsa ham). "
            "Uni bosgan har qanday kishi sizga aynan shu chatda anonim xabar yuborishi "
            "mumkin -- siz ularning kimligini ko'rmaysiz.\n"
            "Xabar ostidagi Reply tugmasini bosib yoki oddiy swipe-reply qilib javob "
            "bering -- javobingiz o'sha bitta odamga qaytadi va ularning tomonida ham "
            "haqiqiy javob sifatida ko'rinadi, shu bois bir chatga bir nechta suhbat "
            "kelayotgan bo'lsa ham ularni aralashtirmasdan ushlab turish oson.\n\n"
            "Sizga boshqa birovning havolasi yuborilganmi? Uni bosing, so'ng yozing -- "
            "xabaringiz kimligingiz yashirin holda ularga boradi. Bir xil havolani "
            "keyinroq yana bossangiz, eskisi davom etmaydi, balki yangi suhbat boshlanadi.\n\n"
            "Buyruqlar:\n"
            "/link - qutingiz havolasini olish\n"
            "/newlink - uni qayta tiklash (eskisi bekor bo'ladi)\n"
            "/pause, /resume - yangi suhbatlarni to'xtatish/yoqish\n"
            "/blocked - bloklaganlaringizni ko'rib chiqish\n"
            "/stats - qutingiz uchun tezkor statistikalar\n"
            "/donate - hosting xarajatlariga hissa qo'shish (ixtiyoriy)\n"
            "/cancel - men sizdan kutayotgan ishni to'xtatish (qaysinisini so'rayman)\n"
            "/en, /uz, /rus - tilni almashtirish (yoki /language — u so\'raydi)\n\n"
        ),
        "follow_link_invalid": "Bu havola yaroqsiz — uni ulashgan kishi qayta tiklagan bo'lishi mumkin. Ulardan yangisini so'rang.",
        "follow_link_own": "Bu sizning o'z qutingiz havolasi — o'zingizga yozish shunchaki eslatma bo'lardi! Buning o'rniga uni boshqalarga ulashing: /link",
        "follow_link_blocked": "Siz bu shaxsga xabar yubora olmaysiz.",
        "follow_link_paused": "Bu shaxs hozircha yangi anonim xabarlarni qabul qilmayapti — keyinroq qayta urinib ko'ring.",
        "follow_link_started": (
            "Siz kimgadir anonim tarzda yozyapsiz (#{conv_number}-suhbat) — ular "
            "xabaringizni ko'radi, lekin o'zingiz aytmasangiz, kimligingizni "
            "bilishmaydi.\n\nBirinchi xabaringizni pastda yozing. Undan "
            "keyin javob berayotgan xabaringizni belgilang \u2014 uni suring "
            "yoki ostidagi Javob tugmasini bosing \u2014 shunda gaplaringiz "
            "doim to'g'ri suhbatga tushadi.\n\nBu havolani keyinroq yana "
            "bossangiz, bundan alohida yangi suhbat boshlanadi — bu suhbat esa "
            "ishlashda davom etadi: undagi istalgan xabarga xohlagan paytda "
            "javob bera olasiz."
        ),
        "link_status_paused": "pauza qilingan — yangi suhbatlar qabul qilinmaydi",
        "link_status_active": "xabarlarni qabul qilmoqda",
        "link_message": (
            "Anonim qutingiz havolasi ({status}):\n"
            "<code>{url}</code>\n\n"
            "Nusxalash uchun bosing, so'ng istalgan joyga joylashtiring — uni ochgan "
            "har kim sizga bu yerda kimligini ko'rsatmasdan xabar yubora oladi."
        ),
        "link_button_pause": "⏸️ Pauza",
        "link_button_resume": "▶️ Davom ettirish",
        "link_button_newlink": "🔄 Yangi havola",
        "anonlink_no_link_yet": "Hali havola yo'q — avval /link yuboring.",
        "anonlink_paused_answer": "Pauza qilindi.",
        "anonlink_resumed_answer": "Davom ettirildi.",
        "anonlink_newlink_answer": "Yangi havola yaratildi — eski havola endi yangi suhbat boshlamaydi.",
        "newlink_message": "Yangi havola (eskisi endi yangi suhbat boshlamaydi):\n<code>{url}</code>",
        "pause_message": (
            "Pauza qilindi — /resume buyrug'igacha havolangiz yangi suhbat boshlamaydi. "
            "Allaqachon boshlangan suhbatlar odatdagidek davom etadi."
        ),
        "resume_message": "Davom ettirildi — havolangiz yana yangi suhbatlarni qabul qilmoqda.",
        "stats_message": "Sizga {followers} ta turli mehmon yozgan, jami {conversations} ta suhbat orqali.",
        "blocked_none": "Siz hech kimni bloklamagansiz.",
        "blocked_header": "Bloklangan mehmonlar:",
        "blocked_guest_line": "  \U0001f6ab {conversations}-suhbatdagi mehmon",
        "blocked_guest_line_unknown": "  \U0001f6ab Mehmon (suhbat qayd etilmagan)",
        "blocked_unblock_button": "↩️ Blokdan chiqarish ({conversations}-suhbat)",
        "blocked_unblock_button_unknown": "↩️ Blokdan chiqarish",
        "reply_button": "↩️ Javob berish",
        "block_button": "\U0001f6ab Bloklash",
        "reply_prompt": "✍️ #{conv_number}-suhbatda javob yozyapsiz. Xabar:\n{quote}",
        "reply_placeholder": "Javobingiz...",
        "opening_placeholder": "Xabaringiz...",
        "not_your_conversation": "Bu sizning suhbatingiz emas.",
        "blocked_answer": "Bloklandi.",
        "unblock_button_labelled": "↩️ #{conv_number}-suhbatni blokdan chiqarish",
        "too_fast": "Xabarlarni men yetkazishga ulgurmayotgan tezlikda yuboryapsiz — taxminan {seconds} soniyadan so'ng qayta urinib ko'ring.",
        "edit_not_relayed": (
            "Bu xabarni allaqachon yetkazgan edim, shuning uchun tahrir unga bormadi — "
            "unda hali dastlabki matn turibdi. Tuzatishni o'sha xabarga javob qilib qayta yuboring."
        ),
        "unblocked_answer": "Blokdan chiqarildi.",
        "delivery_blocked": "Xabaringiz yetkazilmadi.",
        "inbox_gone": "Bu quti endi mavjud emas.",
        "incoming_header": "\U0001f4e9 #{conv_number}-suhbat",
        "incoming_header_follower": "\U0001f4ec #{conv_number}-suhbat",
        "delivery_forbidden": (
            "Buni yetkazib bo'lmadi — bu bot o'zi botni ishga tushirmagan kishiga "
            "xabar yubora olmaydi, bu shaxs esa hali tushirmagan. Hech narsa yuborilmadi."
        ),
        "delivery_failed": "Bu xabarni yetkazib bo'lmadi: {error}",
        "sent_confirmation": "Yuborildi ✅",
        "reply_no_match": "Bu javobni biror suhbatga moslab bo'lmadi.",
        "must_reply": (
            "Qaysi xabarga javob berayotganingizni belgilang — xabarni suring yoki "
            "uning ostidagi \u21a9\ufe0f Javob tugmasini bosing — shunda bu qaysi "
            "suhbatga tegishli ekanini bilaman.\n\nYoki quyidagi tugma bilan "
            "shundayligicha yuboring."
        ),
        "must_reply_button": "Baribir yuborilsin",
        "must_reply_ambiguous": (
            "Qaysi xabarga javob berayotganingizni belgilang \u2014 xabarni "
            "suring yoki uning ostidagi \u21a9\ufe0f Javob tugmasini bosing."
            "\n\nBu chatda bir nechta suhbat ochiq, shuning uchun qaysi biriga "
            "tegishli ekani ko'rsatilmagan xabar boshqa odamga ketib qolishi "
            "mumkin. Hech narsa yuborilmadi."
        ),
        "must_reply_expired": "Bu xabar endi yuborishni kutmayapti — qaytadan yuboring.",
        "update_soon_try_later": "🔧 Hozir yangilanaman, shuning uchun yangi ish boshlay olmayman — taxminan {minutes} daqiqadan so'ng qaytadan urinib ko'ring. Qaytganimda o'zim xabar beraman.",
        "update_soon_try_later_soon": "🔧 Hozir yangilanmoqdaman, shuning uchun yangi ish boshlay olmayman — birozdan so'ng qaytadan urinib ko'ring. Qaytganimda o'zim xabar beraman.",
        "update_will_reset": "🔧 Diqqat: men yangilanmoqchiman va hozir boshlagan ishingiz bekor qilinadi. Bir necha daqiqadan so'ng qaytadan boshlashingiz mumkin.",
        "update_done_try_now": "✅ Yangilanish tugadi — endi qaytadan urinib ko'rishingiz mumkin.",
        "reply_forbidden": "Javobingizni yetkazib bo'lmadi — ular sizni bloklagan yoki botni tark etgan bo'lishi mumkin.",
        "reply_failed": "Javobingizni yetkazib bo'lmadi: {error}",
        "delivered_confirmation": "Yetkazildi ↩️",
        "reply_stale": (
            "Bu xabar mening yozuvlarimda yo'q, shuning uchun bu qaysi suhbatga "
            "javob ekanini bilmayapman. Men shu yerga yetkazgan xabarlardan biriga "
            "javob bering — uni suring yoki ostidagi ↩️ tugmasini bosing. "
            "Hech narsa yuborilmadi."
        ),
        "generic_nudge": "Bu nima uchunligini tushunmadim — agar sizga kimdir havola yuborgan bo'lsa, avval o'shani bosing. O'z qutingiz kerakmi? /link yuboring.",
        "unknown_command": "Bu buyruqni tanimadim. Nima qila olishimni bilish uchun /help yuboring.",
    },
    "ru": {
        "flood_wait": "Ты отправляешь быстрее, чем я успеваю -- подожди примерно {seconds} секунд(ы) и продолжай.",
        "sibling_blurb": "Тоже часть этой семьи ботов, смотри ниже \U0001f447",
        "donation_nudge": (
            "💙 Если этот бот оказался полезным: расходы на хостинг/API покрывает тот, "
            "кто его запустил, а /donate — это совершенно необязательный способ помочь "
            "ему остаться на плаву. Никакого давления в любом случае!"
        ),
        "donate_unknown_currency": 'Неизвестная валюта "{currency}" — попробуйте xtr или usd.',
        "donate_currency_not_configured": "Пожертвования в {currency} на этом боте пока не настроены — попробуйте Stars.",
        "donate_invalid_amount": "Это некорректная сумма — попробуйте, например, /donate 500 или /donate 5 usd.",
        "donate_prompt": (
            "Спасибо за вклад — эти средства идут прямо на хостинг и API этого "
            "бота. Выберите сумму ниже или нажмите «Другое», чтобы ввести свою "
            "(также можно сразу отправить /donate <число> [usd])."
        ),
        "donate_custom_button": "✏️ Другое {symbol}",
        "donate_too_many_stars": "Это очень много звёзд! Пусть будет меньше {max} ⭐ за одно пожертвование.",
        "donate_out_of_range": "Пожертвования в {currency} должны быть в диапазоне от {lo} до {hi} {symbol}.",
        "donate_invoice_title": "Угостите бота кофе ☕",
        "donate_invoice_description": "Разовое добровольное пожертвование на хостинг. Спасибо!",
        "donate_invoice_label": "Пожертвование",
        "donate_invoice_error": "⚠️ Telegram не смог создать этот счёт: {error}",
        "stars_unit": "Stars (звёзды)",
        "donate_custom_ask": "Сколько {unit} вы хотите пожертвовать? Ответьте числом.",
        "donate_invalid_amount_retry": "Это некорректная сумма — отправьте /donate, чтобы попробовать снова.",
        "donate_thanks": "🙏 Спасибо за {amount} ⭐ — это по-настоящему ценно!",
        "language_set_confirmation": "✅ Язык изменён на русский.",
        "cancel_header": "\u274c \u041e\u0442\u043c\u0435\u043d\u0435\u043d\u043e:",
        "cancel_nothing": "\u041e\u0442\u043c\u0435\u043d\u044f\u0442\u044c \u043d\u0435\u0447\u0435\u0433\u043e -- \u044f \u043d\u0438\u0447\u0435\u0433\u043e \u043e\u0442 \u0432\u0430\u0441 \u043d\u0435 \u0436\u0434\u0430\u043b.",
        "cancel_ask": "Что остановить? Вот что я жду:",
        "cancel_kept": "Хорошо -- ничего не отменено.",
        "cancel_reply_box_freed": "Поле ответа снова свободно.",
        "cancel_button_all": "❌ Всё",
        "cancel_button_none": "↩️ Ничего, продолжаем",
        "cancel_button_donation": "💸 Сумма пожертвования",
        "cancel_item_donation": "\u0441\u0443\u043c\u043c\u0430 \u043f\u043e\u0436\u0435\u0440\u0442\u0432\u043e\u0432\u0430\u043d\u0438\u044f, \u043a\u043e\u0442\u043e\u0440\u0443\u044e \u044f \u0437\u0430\u043f\u0440\u043e\u0441\u0438\u043b",
        "cancel_item_stale_prompt": "старый запрос, который всё ещё ждал ответа",
        "cancel_item_anon_session": "\u043e\u0442\u043a\u0440\u044b\u0442\u044b\u0439 \u0430\u043d\u043e\u043d\u0438\u043c\u043d\u044b\u0439 \u0447\u0430\u0442 -- \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u0441\u0441\u044b\u043b\u043a\u0443 \u0441\u043d\u043e\u0432\u0430, \u0447\u0442\u043e\u0431\u044b \u043d\u0430\u0447\u0430\u0442\u044c \u043d\u043e\u0432\u044b\u0439",
        "cancel_button_anon_session": "💬 Анонимный чат, в котором вы",
        "cancel_item_reply_prompt": "\u043e\u0442\u0432\u0435\u0442, \u043a\u043e\u0442\u043e\u0440\u044b\u0439 \u0432\u044b \u043f\u0438\u0441\u0430\u043b\u0438",
        "cancel_button_reply_prompt": "↩️ Ответ, который вы писали",
        "start_greeting": "Привет! Этот бот управляет анонимными почтовыми ящиками для вопросов.\n\n",
        "help_text": (
            "Есть два способа пользоваться этим ботом:\n\n"
            "Заведите свой ящик -- /link даёт вам постоянную ссылку. Разместите её "
            "где угодно на виду (в био, канале, истории — где хотите). Любой, кто по "
            "ней перейдёт, сможет отправить вам анонимное сообщение прямо в этот чат "
            "-- вы не увидите, кто это.\n"
            "Отвечайте, нажав кнопку Reply под сообщением, или просто смахните для "
            "ответа как обычно -- ваш ответ уйдёт именно этому человеку и появится "
            "у него как настоящий ответ, поэтому легко не путать несколько бесед, "
            "даже если они приходят в один и тот же чат.\n\n"
            "Вам прислали чужую ссылку? Перейдите по ней, затем просто напишите -- "
            "ваше сообщение уйдёт адресату, а личность останется скрытой. Если позже "
            "перейти по той же ссылке снова, начнётся новая беседа, а не продолжение старой.\n\n"
            "Команды:\n"
            "/link - получить ссылку на свой ящик\n"
            "/newlink - сбросить её (старая перестанет работать)\n"
            "/pause, /resume - остановить/разрешить новые беседы\n"
            "/blocked - посмотреть, кого вы заблокировали\n"
            "/stats - быстрая статистика по вашему ящику\n"
            "/donate - помочь с расходами на хостинг (совершенно необязательно)\n"
            "/cancel - остановить то, чего я от вас жду (спрошу, что именно)\n"
            "/en, /uz, /rus - сменить язык (или /language — он спрашивает)\n\n"
        ),
        "follow_link_invalid": "Эта ссылка недействительна — возможно, тот, кто ею поделился, сбросил её. Попросите у него новую.",
        "follow_link_own": "Это ссылка на ваш собственный ящик — писать самому себе было бы просто заметкой для себя! Поделитесь ею с другими: /link",
        "follow_link_blocked": "Вы не можете написать этому человеку.",
        "follow_link_paused": "Этот человек сейчас не принимает новые анонимные сообщения — попробуйте позже.",
        "follow_link_started": (
            "Вы анонимно пишете кому-то (беседа #{conv_number}) — он увидит ваше "
            "\u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435, \u043d\u043e \u043d\u0435 \u0443\u0437\u043d\u0430\u0435\u0442, \u043a\u0442\u043e \u0432\u044b, \u0435\u0441\u043b\u0438 \u0432\u044b \u0441\u0430\u043c\u0438 \u043d\u0435 \u0441\u043a\u0430\u0436\u0435\u0442\u0435."
            "\n\n\u041d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 \u043f\u0435\u0440\u0432\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u043d\u0438\u0436\u0435. \u0414\u0430\u043b\u044c\u0448\u0435 "
            "\u043e\u0442\u0432\u0435\u0447\u0430\u0439\u0442\u0435 \u043d\u0430 \u0442\u043e \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435, \u043a\u043e\u0442\u043e\u0440\u043e\u043c\u0443 \u043e\u0442\u0432\u0435\u0447\u0430\u0435\u0442\u0435 \u2014 "
            "\u0441\u0432\u0430\u0439\u043f\u043d\u0438\u0442\u0435 \u0435\u0433\u043e \u0438\u043b\u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u041e\u0442\u0432\u0435\u0442\u0438\u0442\u044c \u043f\u043e\u0434 \u043d\u0438\u043c, "
            "\u0447\u0442\u043e\u0431\u044b \u0441\u043b\u043e\u0432\u0430 \u0432\u0441\u0435\u0433\u0434\u0430 \u043f\u043e\u043f\u0430\u0434\u0430\u043b\u0438 \u0432 \u043d\u0443\u0436\u043d\u0443\u044e \u0431\u0435\u0441\u0435\u0434\u0443.\n\n"
            "\u0415\u0441\u043b\u0438 \u043f\u0435\u0440\u0435\u0439\u0442\u0438 \u043f\u043e \u044d\u0442\u043e\u0439 \u0441\u0441\u044b\u043b\u043a\u0435 \u0441\u043d\u043e\u0432\u0430 \u043f\u043e\u0437\u0436\u0435, \u043d\u0430\u0447\u043d\u0451\u0442\u0441\u044f \u043e\u0442\u0434\u0435\u043b\u044c\u043d\u0430\u044f \u043d\u043e\u0432\u0430\u044f \u0431\u0435\u0441\u0435\u0434\u0430 \u2014 "
            "\u0430 \u044d\u0442\u0430 \u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u0442 \u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c: \u043e\u0442\u0432\u0435\u0447\u0430\u0439\u0442\u0435 \u043d\u0430 \u043b\u044e\u0431\u043e\u0435 \u0435\u0451 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u043a\u043e\u0433\u0434\u0430 \u0443\u0433\u043e\u0434\u043d\u043e."
        ),
        "link_status_paused": "на паузе — новые беседы не принимаются",
        "link_status_active": "принимает сообщения",
        "link_message": (
            "Ссылка на ваш анонимный ящик ({status}):\n"
            "<code>{url}</code>\n\n"
            "Нажмите, чтобы скопировать, и разместите где угодно — любой, кто её "
            "откроет, сможет написать вам сюда, а вы не увидите, кто это."
        ),
        "link_button_pause": "⏸️ Пауза",
        "link_button_resume": "▶️ Возобновить",
        "link_button_newlink": "🔄 Новая ссылка",
        "anonlink_no_link_yet": "Ссылки пока нет — сначала отправьте /link.",
        "anonlink_paused_answer": "На паузе.",
        "anonlink_resumed_answer": "Возобновлено.",
        "anonlink_newlink_answer": "Создана новая ссылка — старая больше не начинает новые беседы.",
        "newlink_message": "Новая ссылка (старая больше не начинает новые беседы):\n<code>{url}</code>",
        "pause_message": (
            "На паузе — ваша ссылка не будет начинать новые беседы до /resume. "
            "Уже идущие беседы продолжают работать как обычно."
        ),
        "resume_message": "Возобновлено — ваша ссылка снова принимает новые беседы.",
        "stats_message": "Вам писали {followers} разных гостей, всего {conversations} беседы(бесед).",
        "blocked_none": "Вы никого не заблокировали.",
        "blocked_header": "Заблокированные гости:",
        "blocked_guest_line": "  \U0001f6ab Гость из бесед(ы) {conversations}",
        "blocked_guest_line_unknown": "  \U0001f6ab Гость (бесед не найдено)",
        "blocked_unblock_button": "↩️ Разблокировать (беседа {conversations})",
        "blocked_unblock_button_unknown": "↩️ Разблокировать",
        "reply_button": "↩️ Ответить",
        "block_button": "\U0001f6ab Заблокировать",
        "reply_prompt": "✍️ Отвечаете в беседе #{conv_number}, на сообщение:\n{quote}",
        "reply_placeholder": "Ваш ответ...",
        "opening_placeholder": "Ваше сообщение...",
        "not_your_conversation": "Это не ваша беседа.",
        "blocked_answer": "Заблокировано.",
        "unblock_button_labelled": "↩️ Разблокировать беседу #{conv_number}",
        "too_fast": "Вы отправляете быстрее, чем я успеваю передавать — подождите около {seconds} сек. и попробуйте снова.",
        "edit_not_relayed": (
            "Это сообщение я уже передал, поэтому правка до собеседника не дошла — "
            "у него прежний текст. Отправьте исправление ещё раз ответом на него."
        ),
        "unblocked_answer": "Разблокирован.",
        "delivery_blocked": "Ваше сообщение не удалось доставить.",
        "inbox_gone": "Этого ящика больше не существует.",
        "incoming_header": "\U0001f4e9 Беседа #{conv_number}",
        "incoming_header_follower": "\U0001f4ec Беседа #{conv_number}",
        "delivery_forbidden": (
            "Не удалось доставить — этот бот не может написать тому, кто сам его "
            "не запускал, а этот человек ещё не запускал. Ничего не отправлено."
        ),
        "delivery_failed": "Не удалось доставить это сообщение: {error}",
        "sent_confirmation": "Отправлено ✅",
        "reply_no_match": "Не удалось сопоставить этот ответ с какой-либо беседой.",
        "must_reply": (
            "Ответьте на то сообщение, которому отвечаете — свайпните его или "
            "нажмите \u21a9\ufe0f Ответить под ним — чтобы я понял, к какой беседе "
            "это относится.\n\nИли отправьте как есть кнопкой ниже."
        ),
        "must_reply_button": "\u0412\u0441\u0451 \u0440\u0430\u0432\u043d\u043e \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c",
        "must_reply_ambiguous": (
            "\u041e\u0442\u0432\u0435\u0442\u044c\u0442\u0435 \u043d\u0430 \u0442\u043e \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435, \u043a\u043e\u0442\u043e\u0440\u043e\u043c\u0443 \u043e\u0442\u0432\u0435\u0447\u0430\u0435\u0442\u0435 \u2014 "
            "\u0441\u0432\u0430\u0439\u043f\u043d\u0438\u0442\u0435 \u0435\u0433\u043e \u0438\u043b\u0438 \u043d\u0430\u0436\u043c\u0438\u0442\u0435 \u21a9\ufe0f \u041e\u0442\u0432\u0435\u0442\u0438\u0442\u044c \u043f\u043e\u0434 \u043d\u0438\u043c."
            "\n\n\u0412 \u044d\u0442\u043e\u043c \u0447\u0430\u0442\u0435 \u043e\u0442\u043a\u0440\u044b\u0442\u043e \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e \u0431\u0435\u0441\u0435\u0434, \u043f\u043e\u044d\u0442\u043e\u043c\u0443 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u0431\u0435\u0437 \u0443\u043a\u0430\u0437\u0430\u043d\u0438\u044f \u0431\u0435\u0441\u0435\u0434\u044b "
            "\u043c\u043e\u0436\u0435\u0442 \u0443\u0439\u0442\u0438 \u043d\u0435 \u0442\u043e\u043c\u0443 \u0447\u0435\u043b\u043e\u0432\u0435\u043a\u0443. \u041d\u0438\u0447\u0435\u0433\u043e \u043d\u0435 \u043e\u0442\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u043e."
        ),
        "must_reply_expired": "Это сообщение больше не ждёт отправки — напишите его заново.",
        "update_soon_try_later": '🔧 Сейчас меня обновляют, поэтому я не могу начать ничего нового — попробуйте снова примерно через {minutes} мин. Я напишу, когда вернусь.',
        "update_soon_try_later_soon": '🔧 Сейчас меня обновляют, поэтому я не могу начать ничего нового — попробуйте снова чуть позже. Я напишу, когда вернусь.',
        "update_will_reset": '🔧 Внимание: меня скоро обновят, и то, что вы сейчас начали, будет сброшено. Через несколько минут сможете начать заново.',
        "update_done_try_now": '✅ Обновление завершено — можете пробовать снова.',
        "reply_forbidden": "Не удалось доставить ваш ответ — возможно, вас заблокировали или человек покинул бота.",
        "reply_failed": "Не удалось доставить ваш ответ: {error}",
        "delivered_confirmation": "Доставлено ↩️",
        "reply_stale": (
            "Этого сообщения нет в моих записях, поэтому я не могу понять, какой "
            "беседе оно отвечает. Ответьте на одно из сообщений, которые я сюда "
            "доставил — свайпните его или нажмите ↩️ под ним. Ничего не отправлено."
        ),
        "generic_nudge": "Не совсем понял, для чего это -- если кто-то прислал вам ссылку, сначала перейдите по ней. Хотите свой ящик? Отправьте /link.",
        "unknown_command": "Я не знаю такую команду. Отправь /help, чтобы увидеть, что я умею.",
    },
}


def t(lang: str | None, key: str, **kwargs) -> str:
    table = STRINGS.get(lang) or STRINGS["en"]
    template = table.get(key) or STRINGS["en"].get(key, key)
    return template.format(**kwargs) if kwargs else template


async def get_lang(user_id: int, context) -> str:
    """Cached in context.user_data to avoid a DB round-trip on every handler
    call. Falls back to "en" for a user who hasn't chosen a language yet
    (only reachable outside /start's first-run gate, e.g. someone who sends
    a link before ever running /start)."""
    cached = context.user_data.get("lang")
    if cached:
        return cached
    lang = await asyncio.to_thread(db.get_user_language, user_id) or "en"
    context.user_data["lang"] = lang
    return lang
