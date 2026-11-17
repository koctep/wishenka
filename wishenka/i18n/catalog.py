"""Centralized bilingual translation catalog (RU/EN) and lookup helper."""

from __future__ import annotations

import logging
from typing import Any

from wishenka.i18n.locale import DEFAULT_LOCALE, SupportedLocale

logger = logging.getLogger("wishenka.i18n")

CATALOG: dict[SupportedLocale, dict[str, str]] = {
    "en": {
        # Mini App navigation and shell
        "nav.settings": "Settings",
        "nav.back": "Back",
        "nav.loading": "Loading",
        # Settings page and language selector
        "settings.page_title": "Settings — Wishenka",
        "settings.title": "Settings",
        "settings.language_heading": "Interface language",
        "settings.language_description": (
            "Applies to Mini App, Telegram bot replies, and notifications."
        ),
        "settings.locale_ru": "Русский",
        "settings.locale_en": "English",
        "settings.source_auto": "Automatic (Telegram client)",
        "settings.source_explicit": "Selected manually",
        "settings.current_source_label": "Current mode:",
        "settings.save_error": "Could not update language. Please try again.",
        "settings.invalid_locale": "Unsupported language selected.",
        "settings.back_home": "Back to Mini App",
        "settings.birthdate_heading": "Personal preferences & birthdate",
        "settings.birthdate_description": (
            "Your manual birthdate choice takes priority over Telegram sync. Year is optional."
        ),
        "settings.birthdate_day": "Day",
        "settings.birthdate_month": "Month",
        "settings.birthdate_year": "Year (optional)",
        "settings.birthdate_save": "Save birthdate",
        "settings.birthdate_clear": "Clear",
        "settings.birthdate_empty": "Not set",
        "settings.birthdate_source_explicit": "Set manually",
        "settings.birthdate_source_auto": "From Telegram",
        "settings.invalid_birthdate": "Please enter a valid calendar birthdate.",
        "settings.birthday_reminders_heading": "Birthday reminders",
        "settings.birthday_reminders_description": (
            "Disable to pause birthday reminders without deleting saved dates."
        ),
        "settings.birthday_reminders_label": "Send birthday reminders",
        "settings.notifications_heading": "Global notification preferences",
        "settings.notifications_description": (
            "Default rules for all wishlists unless overridden per wishlist."
        ),
        "settings.category.wishlist_changes": "Wish & wishlist changes",
        "settings.category.reservation_changes": "Reservation confirmations & updates",
        "settings.category.gift_received": "Gift received notifications",
        "settings.category.reminders": "Wishlist occasion reminders",
        "settings.category.birthday_reminders": "Birthday reminders",
        "settings.wishlists_heading": "Per-wishlist notification overrides",
        "settings.wishlists_description": (
            "List overrides take precedence over global profile settings."
        ),
        "settings.wishlists_empty": "No accessible wishlists yet.",
        "settings.state.enabled": "Enabled",
        "settings.state.disabled": "Disabled",
        "settings.state.inherit": "Inherit global",
        "settings.effective_label": "Effective:",
        "settings.invalid_notification_setting": "Invalid notification category or value.",
        "settings.wishlist_not_found": "Wishlist not found or inaccessible.",
        "settings.saved": "Saved.",
        "settings.delete_account_heading": "Delete account",
        "settings.delete_account_description": (
            "Permanently delete your profile, personal wishlists, settings, and active sessions."
        ),
        "settings.delete_account_button": "Delete account",
        "settings.delete_warning": (
            "This action is permanent and cannot be undone. All your personal data will be erased."
        ),
        "settings.delete_summary_personal": "Personal wishlists to be deleted:",
        "settings.delete_summary_transferred": "Collaborative wishlists to transfer ownership:",
        "settings.delete_summary_collab_deleted": "Solo collaborative wishlists to be deleted:",
        "settings.delete_summary_reservations": "Your active/purchased reservations to cancel:",
        "settings.delete_confirm_button": "Confirm permanent deletion",
        "settings.delete_cancel_button": "Cancel",
        "settings.delete_confirmation_required": "Explicit confirmation is required.",
        "settings.delete_completed": (
            "Your account has been permanently deleted and all sessions have been signed out."
        ),
        "settings.delete_failed": "Could not delete account. Please try again.",
        # Telegram bot commands menu (setMyCommands)
        "bot.commands.start": "Open menu and wishlists",
        "bot.commands.help": "How Wishenka works",
        "bot.commands.birthdays": "Birthday reminders",
        "bot.commands.support": "Contact support",
        "bot.commands.reservation_confirmations": "Manage reservation confirmations",
        "bot.commands.cancel": "Cancel current action",
        # Bot entry & help
        "bot.entry.welcome": "Welcome to Wishenka! Create and share wishlists with friends.",
        "bot.entry.unavailable": "This link is unavailable. Choose an action below.",
        "bot.entry.help": (
            "Create and share a wishlist. Givers can reserve wishes while surprises stay secret."
            " To receive confirmations of your own reservation actions,"
            " send /reservation_confirmations on; use off to stop them."
            " Need help or want to send feedback? Select Contact support or send /support."
        ),
        "bot.entry.btn_create": "Create wishlist",
        "bot.entry.btn_collection": "My wishlists",
        "bot.entry.btn_help": "How it works",
        "bot.entry.btn_support": "Contact support",
        "bot.entry.btn_home": "Open Mini App",
        "bot.entry.btn_public": "Open wishlist",
        "bot.entry.btn_birthdays": "Birthdays",
        "bot.entry.confirmations_usage": "Use /reservation_confirmations on or off.",
        "bot.entry.start_first": "Send /start first.",
        "bot.entry.confirmations_on": (
            "Default reservation confirmations enabled; list settings take precedence."
        ),
        "bot.entry.confirmations_off": (
            "Default reservation confirmations disabled; list settings take precedence."
        ),
        # Bot birthdays
        "bot.birthdays.heading": "Birthdays:",
        "bot.birthdays.btn_add": "Add",
        "bot.birthdays.btn_edit": "Edit",
        "bot.birthdays.btn_delete": "Delete",
        "bot.birthdays.cancelled": "Cancelled.",
        "bot.birthdays.enter_name": "Enter a name:",
        "bot.birthdays.action_unavailable": "Action unavailable.",
        "bot.birthdays.enter_date": "Enter date MM-DD:",
        "bot.birthdays.invalid_label": "Enter a name of at most 80 characters.",
        "bot.birthdays.invalid_date": "Invalid date. Enter MM-DD.",
        "bot.birthdays.stale": "Entry has changed.",
        "bot.birthdays.limit": "At most 20 entries are allowed.",
        "bot.birthdays.saved": "Saved.",
        # Bot support
        "bot.support.prompt": (
            "Describe your question, problem, or feedback in one message and send it here.\n"
            "Send /cancel or press the button below to exit support mode."
        ),
        "bot.support.cancel_button": "Cancel",
        "bot.support.support_button": "Contact support",
        "bot.support.cancelled": (
            "Support request cancelled. You can continue sending wishes as usual."
        ),
        "bot.support.empty": (
            "Please send a text message describing your question or issue, or press Cancel."
        ),
        "bot.support.non_text": (
            "Only text messages are supported in support requests. "
            "Please describe your issue in text or press Cancel."
        ),
        "bot.support.too_long": (
            "Your message is too long (maximum {max_len} characters). "
            "Please shorten it and try again, or press Cancel."
        ),
        "bot.support.rate_limited": (
            "You have reached the support request limit. "
            "Please wait about {minutes} min. and try again later."
        ),
        "bot.support.unavailable": (
            "Support is temporarily unavailable and your message could not be delivered. "
            "Please try again later."
        ),
        "bot.support.submitted": (
            "Your message has been sent to support.\nTicket reference: {ticket_ref}"
        ),
        # Bot wish capture
        "bot.capture.field.title": "Title",
        "bot.capture.field.description": "Description",
        "bot.capture.field.link": "Link",
        "bot.capture.field.image_url": "Image URL",
        "bot.capture.field.price": "Price",
        "bot.capture.field.currency": "Currency",
        "bot.capture.field.quantity": "Quantity",
        "bot.capture.field.priority": "Priority",
        "bot.capture.field.category": "Category",
        "bot.capture.field.recipient_user_id": "Recipient ID",
        "bot.capture.field.recipient_name": "Recipient name",
        "bot.capture.btn_clear": "Clear",
        "bot.capture.btn_edit": "Edit",
        "bot.capture.btn_view_full": "View full values",
        "bot.capture.btn_save": "Save",
        "bot.capture.btn_create_wishlist": "Create wishlist",
        "bot.capture.btn_cancel": "Cancel",
        "bot.capture.previous_discarded": "Previous draft discarded.",
        "bot.capture.review_heading": "Review",
        "bot.capture.preview_fallback": (
            "Could not extract all details. Review and enter missing fields manually."
        ),
        "bot.capture.missing_prefix": "Missing: ",
        "bot.capture.title_required": "Title is required.",
        "bot.capture.list_line": "List: {list}",
        "bot.capture.choose_list": "Choose a list",
        "bot.capture.no_lists": "No available list. Create a wishlist or request an invitation.",
        "bot.capture.truncated_notice": (
            "Long values are shortened only in this review; they are saved in full. "
            "Select View full values."
        ),
        "bot.capture.invalid_field": "Invalid {field}. Please try again.",
        "bot.capture.draft_expired": "Draft expired; start again.",
        "bot.capture.empty_input": "Please send a title or link.",
        "bot.capture.too_long": "Message is too long. Please shorten it and try again.",
        "bot.capture.action_error": "Could not save. Please retry.",
        "bot.capture.saved_prefix": "Saved: ",
        "bot.capture.enter_prefix": "Enter: ",
        "bot.capture.choose_field": "Choose field",
        "bot.capture.error_invalid": "Invalid title or fields.\n",
        "bot.capture.error_unavailable": "List unavailable.\n",
        "bot.capture.error_unsafe_url": "Use an http or https URL, or clear the link.\n",
        "bot.capture.cancelled": "Cancelled.",
        "bot.capture.expired": "Expired; start again.",
        # Outgoing notifications & reminders
        "notices.gift_received": (
            "Wish ‘{wish}’ from ‘{wishlist}’ was marked received. "
            "Check your reservation and change it if necessary."
        ),
        "notices.reminder.occasion": "Upcoming occasion: {title} ({date}).",
        "notices.reminder.item_created": "Wish added: {subject}.",
        "notices.reminder.item_updated": "Wish updated: {subject}.",
        "notices.reminder.item_archived": "Wish archived: {subject}.",
        "notices.reminder.item_restored": "Wish restored: {subject}.",
        "notices.reminder.list_updated": "Wishlist updated: {subject}.",
        "notices.reminder.list_archived": "Wishlist archived: {subject}.",
        "notices.reminder.list_restored": "Wishlist restored: {subject}.",
        "notices.reminder.membership_changed": "Wishlist membership changed: {subject}.",
        "notices.reminder.reservation_confirmation": "Your reservation was updated: {subject}.",
        # Mini App client UI
        "miniapp.role.owner": "Owner",
        "miniapp.role.admin": "Admin",
        "miniapp.role.member": "Collaborator",
        "miniapp.role.favorite": "Favorite",
        "miniapp.common.untitled_wishlist": "Untitled wishlist",
        "miniapp.home.title": "Wishlists",
        "miniapp.home.create_wishlist": "Create wishlist",
        "miniapp.home.create_failed": "Could not create wishlist. Try again.",
        "miniapp.home.viewing_history": "Viewing history",
        "miniapp.home.my_wishlists": "My wishlists",
        "miniapp.home.my_wishlists_empty": "No personal wishlists yet",
        "miniapp.home.collaborating": "Collaborating",
        "miniapp.home.collaborating_empty": "No collaborative wishlists yet",
        "miniapp.home.favorites": "Favorites",
        "miniapp.home.favorites_empty": "No favorites yet",
        "miniapp.home.remove": "Remove",
        "miniapp.home.removed_from_favorites": "Removed from favorites",
        "miniapp.home.remove_favorite_failed": "Could not remove from favorites",
        "miniapp.home.load_failed": "Could not load wishlists. Check your session and try again.",
        "miniapp.share.not_configured": "Sharing is not configured",
        "miniapp.share.copy_link": "Copy link",
        "miniapp.share.link_copied": "Link copied",
        "miniapp.share.copy_failed": "Copy failed. Select the link and copy it manually.",
        "miniapp.share.share_telegram": "Share via Telegram",
        "miniapp.share.telegram_opened": "Telegram chooser opened",
        "miniapp.share.telegram_unavailable": "Telegram sharing is unavailable",
        "miniapp.share.public_title": "Public gift-selection link",
        "miniapp.share.replace_public": "Replace public link",
        "miniapp.share.public_replaced": "Old public link no longer works",
        "miniapp.share.replace_public_failed": "Could not replace the public link",
        "miniapp.history.title": "Viewing history",
        "miniapp.history.clear": "Clear history",
        "miniapp.history.cleared": "History cleared",
        "miniapp.history.clear_failed": "Could not clear history",
        "miniapp.history.empty": "No viewing history yet",
        "miniapp.history.viewed_at": "Viewed: {date}",
        "miniapp.history.load_failed": "Could not load history",
        "miniapp.wishlist_settings.heading": "Settings",
        "miniapp.wishlist_settings.field_title": "Title",
        "miniapp.wishlist_settings.field_description": "Description",
        "miniapp.wishlist_settings.field_event": "Event",
        "miniapp.wishlist_settings.field_date": "Date",
        "miniapp.wishlist_settings.save": "Save settings",
        "miniapp.wishlist_settings.cancel": "Cancel",
        "miniapp.wishlist_settings.saved": "Settings saved",
        "miniapp.wishlist_settings.save_failed": (
            "Could not save settings. Your changes are still here."
        ),
        "miniapp.members.heading": "Manage members",
        "miniapp.members.remove": "Remove member",
        "miniapp.members.removed": "Member removed",
        "miniapp.members.remove_failed": "Could not remove member",
        "miniapp.members.make_admin": "Make admin",
        "miniapp.members.remove_admin": "Remove admin",
        "miniapp.members.role_change_failed": "Could not change role",
        "miniapp.members.invite_heading": "Collaborator invitation",
        "miniapp.members.revoke_invite": "Revoke invitation",
        "miniapp.members.invite_revoked": "Old invitation revoked",
        "miniapp.members.revoke_invite_failed": "Could not revoke invitation",
        "miniapp.list.add_favorite": "Add to favorites",
        "miniapp.list.remove_favorite": "Remove from favorites",
        "miniapp.list.added_favorite": "Added to favorites",
        "miniapp.list.removed_favorite": "Removed from favorites",
        "miniapp.list.favorite_failed": "Could not update favorites",
        "miniapp.list.wishes_heading": "Wishes",
        "miniapp.list.wishes_future_update": "Adding wishes will be available in a future update.",
        "miniapp.list.archived_notice": "This wishlist is archived and read-only.",
        "miniapp.list.restore": "Restore wishlist",
        "miniapp.list.restore_failed": "Could not restore wishlist",
        "miniapp.list.load_failed": "Could not load this wishlist",
        "miniapp.deleted.heading": "Recently deleted",
        "miniapp.deleted.days_left": "{days} d. left until permanent deletion",
        "miniapp.deleted.restore": "Restore",
        "miniapp.deleted.restoring": "Restoring...",
        "miniapp.deleted.restored": "Wishlist restored",
        "miniapp.deleted.expired": (
            "Retention window expired; this wishlist can no longer be restored."
        ),
        "miniapp.deleted.restore_failed": "Could not restore deleted wishlist",
        "miniapp.public.loading": "Loading wishlist",
        "miniapp.public.reserve": "Reserve",
        "miniapp.public.reserved": "Reserved",
        "miniapp.public.reserve_failed": "Could not reserve this wish. Please try again.",
        "miniapp.invite.heading": "Collaborator invitation",
        "miniapp.invite.default_name": "wishlist",
        "miniapp.invite.prompt": "Join {name} as a member?",
        "miniapp.invite.confirm": "Confirm joining",
        "miniapp.invite.join_failed": "Could not join. Check your Telegram session or invitation.",
        "miniapp.invite.unavailable": "This invitation is unavailable",
        "miniapp.unavailable.title": "This link is unavailable",
        "miniapp.unavailable.description": "Return to the menu and choose another action.",
        "miniapp.unavailable.home_menu": "Home menu",
        "miniapp.auth.open_in_telegram": "Open this app in Telegram to sign in.",
    },
    "ru": {
        # Mini App navigation and shell
        "nav.settings": "Настройки",
        "nav.back": "Назад",
        "nav.loading": "Загрузка",
        # Settings page and language selector
        "settings.page_title": "Настройки — Вишенка",
        "settings.title": "Настройки",
        "settings.language_heading": "Язык интерфейса",
        "settings.language_description": (
            "Применяется к Mini App, сообщениям бота и уведомлениям."
        ),
        "settings.locale_ru": "Русский",
        "settings.locale_en": "English",
        "settings.source_auto": "Автоматический (язык Telegram)",
        "settings.source_explicit": "Выбран вручную",
        "settings.current_source_label": "Текущий режим:",
        "settings.save_error": "Не удалось обновить язык. Повторите попытку.",
        "settings.invalid_locale": "Выбран неподдерживаемый язык.",
        "settings.back_home": "Вернуться в Mini App",
        "settings.birthdate_heading": "Персональные предпочтения и дата рождения",
        "settings.birthdate_description": (
            "Ручное указание или очистка даты рождения имеют приоритет над синхронизацией с "
            "Telegram. Год указывать необязательно."
        ),
        "settings.birthdate_day": "День",
        "settings.birthdate_month": "Месяц",
        "settings.birthdate_year": "Год (необязательно)",
        "settings.birthdate_save": "Сохранить дату",
        "settings.birthdate_clear": "Очистить",
        "settings.birthdate_empty": "Не указана",
        "settings.birthdate_source_explicit": "Указано вручную",
        "settings.birthdate_source_auto": "Из Telegram",
        "settings.invalid_birthdate": "Укажите корректную календарную дату рождения.",
        "settings.birthday_reminders_heading": "Напоминания о днях рождения",
        "settings.birthday_reminders_description": (
            "При отключении напоминания не отправляются, но сохранённые даты сохраняются."
        ),
        "settings.birthday_reminders_label": "Отправлять напоминания о днях рождения",
        "settings.notifications_heading": "Глобальные настройки уведомлений",
        "settings.notifications_description": (
            "Общие правила для всех вишлистов, если для списка не задано своё переопределение."
        ),
        "settings.category.wishlist_changes": "Изменения желаний и списков",
        "settings.category.reservation_changes": "Подтверждения и изменения броней",
        "settings.category.gift_received": "Уведомления о получении подарка",
        "settings.category.reminders": "Напоминания о событиях вишлиста",
        "settings.category.birthday_reminders": "Напоминания о днях рождения",
        "settings.wishlists_heading": "Настройки по отдельным вишлистам",
        "settings.wishlists_description": (
            "Персональные настройки списка имеют приоритет над глобальными настройками профиля."
        ),
        "settings.wishlists_empty": "Пока нет доступных вишлистов.",
        "settings.state.enabled": "Включено",
        "settings.state.disabled": "Отключено",
        "settings.state.inherit": "Как в общих",
        "settings.effective_label": "Итог:",
        "settings.invalid_notification_setting": "Некорректная категория или значение настройки.",
        "settings.wishlist_not_found": "Вишлист не найден или недоступен.",
        "settings.saved": "Сохранено.",
        "settings.delete_account_heading": "Удаление аккаунта",
        "settings.delete_account_description": (
            "Безвозвратно удалить профиль, личные вишлисты, настройки и все активные сессии."
        ),
        "settings.delete_account_button": "Удалить аккаунт",
        "settings.delete_warning": (
            "Это действие необратимо. Все ваши персональные данные будут удалены навсегда."
        ),
        "settings.delete_summary_personal": "Личных вишлистов к удалению:",
        "settings.delete_summary_transferred": "Совместных списков к передаче владения:",
        "settings.delete_summary_collab_deleted": "Совместных списков без участников к удалению:",
        "settings.delete_summary_reservations": "Ваших активных и купленных броней к снятию:",
        "settings.delete_confirm_button": "Подтвердить удаление навсегда",
        "settings.delete_cancel_button": "Отмена",
        "settings.delete_confirmation_required": "Требуется явное подтверждение удаления.",
        "settings.delete_completed": (
            "Ваш аккаунт безвозвратно удалён, все активные сессии завершены."
        ),
        "settings.delete_failed": "Не удалось удалить аккаунт. Попробуйте ещё раз.",
        # Telegram bot commands menu (setMyCommands)
        "bot.commands.start": "Открыть меню и вишлисты",
        "bot.commands.help": "Как работает Вишенка",
        "bot.commands.birthdays": "Напоминания о днях рождения",
        "bot.commands.support": "Написать в поддержку",
        "bot.commands.reservation_confirmations": "Подтверждения своих броней",
        "bot.commands.cancel": "Отменить текущее действие",
        # Bot entry & help
        "bot.entry.welcome": "Добро пожаловать в Вишенку! Создавайте и делитесь вишлистами.",
        "bot.entry.unavailable": "Ссылка недоступна. Выберите действие ниже.",
        "bot.entry.help": (
            "Создайте и отправьте вишлист. Дарители бронируют желания, сохраняя сюрприз."
            " Чтобы получать подтверждения своих действий с бронью, отправьте"
            " /reservation_confirmations on; для отключения используйте off."
            " Нужна помощь или хотите отправить отзыв? Нажмите «Написать в поддержку»"
            " или отправьте /support."
        ),
        "bot.entry.btn_create": "Создать вишлист",
        "bot.entry.btn_collection": "Мои вишлисты",
        "bot.entry.btn_help": "Как это работает",
        "bot.entry.btn_support": "Написать в поддержку",
        "bot.entry.btn_home": "Открыть Mini App",
        "bot.entry.btn_public": "Открыть вишлист",
        "bot.entry.btn_birthdays": "Дни рождения",
        "bot.entry.confirmations_usage": "Используйте /reservation_confirmations on или off.",
        "bot.entry.start_first": "Сначала отправьте /start.",
        "bot.entry.confirmations_on": (
            "Подтверждения бронирования включены по умолчанию; настройки списка важнее."
        ),
        "bot.entry.confirmations_off": (
            "Подтверждения бронирования выключены по умолчанию; настройки списка важнее."
        ),
        # Bot birthdays
        "bot.birthdays.heading": "Дни рождения:",
        "bot.birthdays.btn_add": "Добавить",
        "bot.birthdays.btn_edit": "Изменить",
        "bot.birthdays.btn_delete": "Удалить",
        "bot.birthdays.cancelled": "Отменено.",
        "bot.birthdays.enter_name": "Введите имя:",
        "bot.birthdays.action_unavailable": "Действие недоступно.",
        "bot.birthdays.enter_date": "Введите дату MM-DD:",
        "bot.birthdays.invalid_label": "Введите имя до 80 символов.",
        "bot.birthdays.invalid_date": "Некорректная дата. Введите MM-DD.",
        "bot.birthdays.stale": "Запись изменилась.",
        "bot.birthdays.limit": "Не более 20 записей.",
        "bot.birthdays.saved": "Сохранено.",
        # Bot support
        "bot.support.prompt": (
            "Опишите ваш вопрос, проблему или отзыв одним сообщением и отправьте его сюда.\n"
            "Отправьте /cancel или нажмите кнопку ниже, чтобы выйти из режима "
            "обращения в поддержку."
        ),
        "bot.support.cancel_button": "Отмена",
        "bot.support.support_button": "Написать в поддержку",
        "bot.support.cancelled": (
            "Обращение в поддержку отменено. Вы можете снова отправлять желания как обычно."
        ),
        "bot.support.empty": (
            "Пожалуйста, отправьте текстовое сообщение с описанием вопроса или нажмите «Отмена»."
        ),
        "bot.support.non_text": (
            "Поддерживаются только текстовые сообщения. "
            "Опишите проблему текстом или нажмите «Отмена»."
        ),
        "bot.support.too_long": (
            "Сообщение слишком длинное (максимум {max_len} символов). "
            "Сократите его и попробуйте снова или нажмите «Отмена»."
        ),
        "bot.support.rate_limited": (
            "Вы достигли лимита обращений в поддержку. "
            "Пожалуйста, подождите около {minutes} мин. и попробуйте позже."
        ),
        "bot.support.unavailable": (
            "Канал поддержки временно недоступен, сообщение не удалось доставить. "
            "Пожалуйста, попробуйте позже."
        ),
        "bot.support.submitted": (
            "Ваше обращение отправлено в поддержку.\nНомер обращения: {ticket_ref}"
        ),
        # Bot wish capture
        "bot.capture.field.title": "Название",
        "bot.capture.field.description": "Описание",
        "bot.capture.field.link": "Ссылка",
        "bot.capture.field.image_url": "Ссылка на изображение",
        "bot.capture.field.price": "Цена",
        "bot.capture.field.currency": "Валюта",
        "bot.capture.field.quantity": "Количество",
        "bot.capture.field.priority": "Приоритет",
        "bot.capture.field.category": "Категория",
        "bot.capture.field.recipient_user_id": "ID получателя",
        "bot.capture.field.recipient_name": "Имя получателя",
        "bot.capture.btn_clear": "Очистить",
        "bot.capture.btn_edit": "Редактировать",
        "bot.capture.btn_view_full": "Посмотреть полностью",
        "bot.capture.btn_save": "Сохранить",
        "bot.capture.btn_create_wishlist": "Создать вишлист",
        "bot.capture.btn_cancel": "Отмена",
        "bot.capture.previous_discarded": "Предыдущий черновик удалён.",
        "bot.capture.review_heading": "Проверьте",
        "bot.capture.preview_fallback": (
            "Не удалось извлечь все данные. Проверьте и заполните поля вручную."
        ),
        "bot.capture.missing_prefix": "Не заполнено: ",
        "bot.capture.title_required": "Необходимо название.",
        "bot.capture.list_line": "Список: {list}",
        "bot.capture.choose_list": "Выберите список",
        "bot.capture.no_lists": (
            "Нет доступных списков. Создайте список или запросите приглашение."
        ),
        "bot.capture.truncated_notice": (
            "Длинные значения сокращены только в обзоре; сохраняются полностью. "
            "Нажмите «Посмотреть полностью»."
        ),
        "bot.capture.invalid_field": "Неверное значение: {field}.",
        "bot.capture.draft_expired": "Черновик истёк; начните заново.",
        "bot.capture.empty_input": "Отправьте название или ссылку.",
        "bot.capture.too_long": "Слишком длинное сообщение. Сократите его и повторите.",
        "bot.capture.action_error": "Не удалось сохранить. Повторите попытку.",
        "bot.capture.saved_prefix": "Сохранено: ",
        "bot.capture.enter_prefix": "Введите: ",
        "bot.capture.choose_field": "Выберите поле",
        "bot.capture.error_invalid": "Проверьте поля.\n",
        "bot.capture.error_unavailable": "Список недоступен.\n",
        "bot.capture.error_unsafe_url": "Укажите ссылку http или https либо очистите поле.\n",
        "bot.capture.cancelled": "Отменено.",
        "bot.capture.expired": "Истекло; начните заново.",
        # Outgoing notifications & reminders
        "notices.gift_received": (
            "Желание «{wish}» из списка «{wishlist}» отмечено как полученное.\n"
            "Проверьте свою бронь и при необходимости измените или отмените её."
        ),
        "notices.reminder.occasion": "Приближается событие: {title} ({date}).",
        "notices.reminder.item_created": "Желание добавлено: {subject}.",
        "notices.reminder.item_updated": "Желание изменено: {subject}.",
        "notices.reminder.item_archived": "Желание архивировано: {subject}.",
        "notices.reminder.item_restored": "Желание восстановлено: {subject}.",
        "notices.reminder.list_updated": "Список изменён: {subject}.",
        "notices.reminder.list_archived": "Список архивирован: {subject}.",
        "notices.reminder.list_restored": "Список восстановлен: {subject}.",
        "notices.reminder.membership_changed": "Изменился состав списка: {subject}.",
        "notices.reminder.reservation_confirmation": "Ваше бронирование изменено: {subject}.",
        # Mini App client UI
        "miniapp.role.owner": "Владелец",
        "miniapp.role.admin": "Администратор",
        "miniapp.role.member": "Соавтор",
        "miniapp.role.favorite": "Избранное",
        "miniapp.common.untitled_wishlist": "Вишлист без названия",
        "miniapp.home.title": "Вишлисты",
        "miniapp.home.create_wishlist": "Создать вишлист",
        "miniapp.home.create_failed": "Не удалось создать вишлист. Попробуйте ещё раз.",
        "miniapp.home.viewing_history": "История просмотров",
        "miniapp.home.my_wishlists": "Мои вишлисты",
        "miniapp.home.my_wishlists_empty": "Пока нет личных вишлистов",
        "miniapp.home.collaborating": "Совместные",
        "miniapp.home.collaborating_empty": "Пока нет совместных вишлистов",
        "miniapp.home.favorites": "Избранные",
        "miniapp.home.favorites_empty": "Пока нет избранных вишлистов",
        "miniapp.home.remove": "Удалить",
        "miniapp.home.removed_from_favorites": "Удалено из избранного",
        "miniapp.home.remove_favorite_failed": "Не удалось удалить из избранного",
        "miniapp.home.load_failed": (
            "Не удалось загрузить вишлисты. Проверьте сессию и попробуйте снова."
        ),
        "miniapp.share.not_configured": "Отправка ссылок не настроена",
        "miniapp.share.copy_link": "Скопировать ссылку",
        "miniapp.share.link_copied": "Ссылка скопирована",
        "miniapp.share.copy_failed": (
            "Не удалось скопировать. Выделите ссылку и скопируйте вручную."
        ),
        "miniapp.share.share_telegram": "Отправить через Telegram",
        "miniapp.share.telegram_opened": "Открыт выбор чата в Telegram",
        "miniapp.share.telegram_unavailable": "Отправка через Telegram недоступна",
        "miniapp.share.public_title": "Публичная ссылка для выбора подарков",
        "miniapp.share.replace_public": "Заменить публичную ссылку",
        "miniapp.share.public_replaced": "Старая публичная ссылка больше не работает",
        "miniapp.share.replace_public_failed": "Не удалось заменить публичную ссылку",
        "miniapp.history.title": "История просмотров",
        "miniapp.history.clear": "Очистить историю",
        "miniapp.history.cleared": "История очищена",
        "miniapp.history.clear_failed": "Не удалось очистить историю",
        "miniapp.history.empty": "История просмотров пока пуста",
        "miniapp.history.viewed_at": "Просмотрено: {date}",
        "miniapp.history.load_failed": "Не удалось загрузить историю",
        "miniapp.wishlist_settings.heading": "Настройки",
        "miniapp.wishlist_settings.field_title": "Название",
        "miniapp.wishlist_settings.field_description": "Описание",
        "miniapp.wishlist_settings.field_event": "Событие",
        "miniapp.wishlist_settings.field_date": "Дата",
        "miniapp.wishlist_settings.save": "Сохранить настройки",
        "miniapp.wishlist_settings.cancel": "Отмена",
        "miniapp.wishlist_settings.saved": "Настройки сохранены",
        "miniapp.wishlist_settings.save_failed": (
            "Не удалось сохранить настройки. Ваши изменения сохранены в форме."
        ),
        "miniapp.members.heading": "Управление участниками",
        "miniapp.members.remove": "Удалить участника",
        "miniapp.members.removed": "Участник удалён",
        "miniapp.members.remove_failed": "Не удалось удалить участника",
        "miniapp.members.make_admin": "Назначить администратором",
        "miniapp.members.remove_admin": "Снять права администратора",
        "miniapp.members.role_change_failed": "Не удалось изменить роль",
        "miniapp.members.invite_heading": "Приглашение соавтора",
        "miniapp.members.revoke_invite": "Отозвать приглашение",
        "miniapp.members.invite_revoked": "Старое приглашение отозвано",
        "miniapp.members.revoke_invite_failed": "Не удалось отозвать приглашение",
        "miniapp.list.add_favorite": "Добавить в избранное",
        "miniapp.list.remove_favorite": "Удалить из избранного",
        "miniapp.list.added_favorite": "Добавлено в избранное",
        "miniapp.list.removed_favorite": "Удалено из избранного",
        "miniapp.list.favorite_failed": "Не удалось обновить избранное",
        "miniapp.list.wishes_heading": "Желания",
        "miniapp.list.wishes_future_update": "Добавление желаний появится в следующем обновлении.",
        "miniapp.list.archived_notice": "Этот вишлист в архиве и доступен только для чтения.",
        "miniapp.list.restore": "Восстановить вишлист",
        "miniapp.list.restore_failed": "Не удалось восстановить вишлист",
        "miniapp.list.load_failed": "Не удалось загрузить этот вишлист",
        "miniapp.deleted.heading": "Недавно удалённые",
        "miniapp.deleted.days_left": "Осталось {days} дн. до окончательного удаления",
        "miniapp.deleted.restore": "Восстановить",
        "miniapp.deleted.restoring": "Восстановление...",
        "miniapp.deleted.restored": "Вишлист восстановлен",
        "miniapp.deleted.expired": "Срок удержания истёк, вишлист больше нельзя восстановить.",
        "miniapp.deleted.restore_failed": "Не удалось восстановить удалённый вишлист",
        "miniapp.public.loading": "Загрузка вишлиста",
        "miniapp.public.reserve": "Забронировать",
        "miniapp.public.reserved": "Забронировано",
        "miniapp.public.reserve_failed": "Не удалось забронировать желание. Попробуйте ещё раз.",
        "miniapp.invite.heading": "Приглашение соавтора",
        "miniapp.invite.default_name": "вишлисту",
        "miniapp.invite.prompt": "Присоединиться к {name} как соавтор?",
        "miniapp.invite.confirm": "Подтвердить участие",
        "miniapp.invite.join_failed": (
            "Не удалось присоединиться. Проверьте сессию Telegram или приглашение."
        ),
        "miniapp.invite.unavailable": "Это приглашение недоступно",
        "miniapp.unavailable.title": "Ссылка недоступна",
        "miniapp.unavailable.description": "Вернитесь в меню и выберите другое действие.",
        "miniapp.unavailable.home_menu": "Главное меню",
        "miniapp.auth.open_in_telegram": "Откройте приложение в Telegram, чтобы войти.",
    },
}


def miniapp_catalog() -> dict[SupportedLocale, dict[str, str]]:
    """Return the bilingual Mini App dictionary projected from CATALOG."""
    prefixes = ("nav.", "miniapp.")
    return {
        locale: {key: value for key, value in entries.items() if key.startswith(prefixes)}
        for locale, entries in CATALOG.items()
    }


def t(key: str, locale: str | None = DEFAULT_LOCALE, **kwargs: Any) -> str:
    """Render a translated message by key and locale with safe fallback to English or key."""
    target: SupportedLocale = "ru" if locale == "ru" else DEFAULT_LOCALE
    template = CATALOG.get(target, {}).get(key)
    if template is None:
        fallback_template = CATALOG.get(DEFAULT_LOCALE, {}).get(key)
        if fallback_template is not None:
            logger.warning(
                "Missing translation key %s for locale %s",
                key,
                target,
                extra={
                    "event": "i18n_missing_translation_key",
                    "i18n_key": key,
                    "locale": target,
                    "fallback_locale": DEFAULT_LOCALE,
                },
            )
            template = fallback_template
        else:
            logger.warning(
                "Missing translation key %s for locale %s",
                key,
                target,
                extra={
                    "event": "i18n_missing_translation_key",
                    "i18n_key": key,
                    "locale": target,
                    "fallback_locale": "key",
                },
            )
            return key
    if kwargs:
        return template.format(**kwargs)
    return template
