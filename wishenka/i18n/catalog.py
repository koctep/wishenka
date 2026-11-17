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
    },
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
