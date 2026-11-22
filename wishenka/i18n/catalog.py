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
        "settings.saving": "Saving…",
        "settings.rejected": "Not saved. The previous value is kept; please try again.",
        "settings.not_saved_after_error": (
            "Not saved: the request failed. The current value was checked and is unchanged."
        ),
        "settings.confirmed_after_error": (
            "The server reported an error, but the new value was checked and is in effect."
        ),
        "settings.refreshed": "The current value was checked and is shown.",
        "settings.unknown_state": (
            "Could not confirm the current value. Use Retry to check it again."
        ),
        "settings.retry": "Retry",
        "settings.reload": "Reload page",
        "settings.locale_reload_needed": (
            "The language was changed on the server. Reload the page to apply it."
        ),
        "settings.birthdate_current_label": "Current birthday:",
        "settings.birthdate_priority_hint": (
            "The year is optional. A date saved here is not overwritten by Telegram later."
        ),
        "settings.precedence_hint": (
            "These are defaults. A choice for a single wishlist below takes precedence; "
            "“Inherit global” follows these defaults."
        ),
        "settings.delete_preview_failed": "Could not load the deletion summary. Please try again.",
        "settings.delete_unknown": (
            "The result of deletion is unknown. Reload the page to check the account status."
        ),
        "settings.deleting": "Deleting…",
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
        "notices.receipt_reverted": (
            "Receipt mark for wish ‘{wish}’ from ‘{wishlist}’ was cancelled or corrected. "
            "Check your reservation and keep or update it if needed."
        ),
        "notices.item_quantity_overbooked": (
            "Requested quantity for wish ‘{wish}’ from ‘{wishlist}’ was reduced. "
            "Check your reservation and adjust or cancel it if needed."
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
        "miniapp.home.lead": "Your lists, shared plans, and saved favorites in one place.",
        "miniapp.home.create_wishlist": "Create wishlist",
        "miniapp.home.create_failed": "Could not create wishlist. Try again.",
        "miniapp.home.viewing_history": "Viewing history",
        "miniapp.home.reservations_hint": "Active and purchased gift promises",
        "miniapp.home.my_wishlists": "My wishlists",
        "miniapp.home.my_wishlists_sub": "Lists you created and manage",
        "miniapp.home.my_wishlists_empty": "No personal wishlists yet",
        "miniapp.home.my_wishlists_empty_hint": (
            "Tap Create wishlist above to start your first personal list."
        ),
        "miniapp.home.collaborating": "Collaborating",
        "miniapp.home.collaborating_sub": (
            "Shared lists where you co-edit as admin or collaborator"
        ),
        "miniapp.home.collaborating_empty": "No collaborative wishlists yet",
        "miniapp.home.collaborating_empty_hint": (
            "Ask a list owner for an invitation link to co-edit a wishlist together."
        ),
        "miniapp.home.favorites": "Favorites",
        "miniapp.home.favorites_sub": "Friends' and family wishlists saved for quick access",
        "miniapp.home.favorites_empty": "No favorites yet",
        "miniapp.home.favorites_empty_hint": (
            "Open someone's shared wishlist link and add it to favorites to keep it handy."
        ),
        "miniapp.home.deleted_sub": "Lists you can restore before the retention window expires",
        "miniapp.home.open_wishlist": "Open",
        "miniapp.home.open_wishlist_named": "Open: {name}",
        "miniapp.home.remove": "Remove",
        "miniapp.home.remove_favorite": "Remove from favorites",
        "miniapp.home.remove_favorite_named": "Remove from favorites: {name}",
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
        "miniapp.share.public_hint": (
            "Gift givers can view wishes and reserve gifts secretly, but cannot edit the list."
        ),
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
        "miniapp.wishlist_settings.subtitle": "Update the details of this wishlist.",
        "miniapp.wishlist_settings.hint_title": "A name people will recognize.",
        "miniapp.wishlist_settings.hint_description": "Add details for your guests.",
        "miniapp.wishlist_settings.hint_event": "Optional occasion name.",
        "miniapp.wishlist_settings.hint_date": "Optional occasion date and time.",
        "miniapp.wishlist_settings.cancelled": "Changes discarded",
        "miniapp.wishlist_settings.field_title": "Title",
        "miniapp.wishlist_settings.field_description": "Description",
        "miniapp.wishlist_settings.field_event": "Event",
        "miniapp.wishlist_settings.field_date": "Date",
        "miniapp.wishlist_settings.save": "Save settings",
        "miniapp.wishlist_settings.cancel": "Cancel",
        "miniapp.wishlist_settings.saved": "Settings saved",
        "miniapp.wishlist_settings.saved_refresh_failed": (
            "Settings saved, but the wishlist could not be refreshed"
        ),
        "miniapp.wishlist_settings.save_failed": (
            "Could not save settings. Your changes are still here."
        ),
        "miniapp.members.heading": "Manage members",
        "miniapp.members.subtitle": "Owners and admins manage the list; collaborators add wishes.",
        "miniapp.members.invite_hint": "Anyone joining can add and edit wishes as a collaborator.",
        "miniapp.members.role_updated": "Member role updated",
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
        "miniapp.list.occasion_prefix": "Occasion:",
        "miniapp.list.wishes_subtitle": "The wishes in this list.",
        "miniapp.list.wishes_empty": "There are no wishes yet.",
        "miniapp.list.restored": "Wishlist restored",
        "miniapp.list.wishes_future_update": "Adding wishes will be available in a future update.",
        "miniapp.list.archived_notice": "This wishlist is archived and read-only.",
        "miniapp.list.restore": "Restore wishlist",
        "miniapp.list.restore_failed": "Could not restore wishlist",
        "miniapp.list.load_failed": "Could not load this wishlist",
        "miniapp.list.refresh_unavailable": "Wishlist temporarily unavailable",
        "miniapp.list.refresh_retry": "Try again",
        "miniapp.list.changed_refresh_failed": (
            "Your change was saved, but the wishlist could not be refreshed"
        ),
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
        # SSR web pages, partials, and UI routes
        "web.common.request_prepare_error": "Could not prepare the request. Please try again.",
        "web.common.wish_busy_error": (
            "The wish is busy; the reservation was not changed. Please try again."
        ),
        "web.common.member_fallback": "Member #{id}",
        "web.common.owner_suffix": "{name} (Owner)",
        "web.common.cancel": "Cancel",
        "web.common.close": "Close",
        "web.common.save": "Save",
        "web.common.delete": "Remove",
        "web.common.edit": "Edit",
        "web.common.add": "Add",
        "web.common.details": "More details",
        "web.wishlist.author": "Author:",
        "web.wishlist.empty": "There are no wishes in this wishlist yet.",
        "web.wishlist.list_changed": "The list has changed. Refreshing.",
        "web.wishlist.archived_heading": "Archived wishes ({count})",
        "web.wishlist.archived_remaining": "Remaining {count}",
        "web.wishlist.restore": "Restore",
        "web.wishlist.gifted_heading": "Gifted ({count})",
        "web.wishlist.gifted_load_error": "Could not load Gifted items. Please refresh the page.",
        "web.wishlist.gifted_for": "For: {name}",
        "web.wishlist.gifted_received_of": "Received: {received} of {requested}",
        "web.wishlist.gifted_approx_date": "≈ {day} (approx. date)",
        "web.wishlist.gifted_act_qty": "{quantity} pcs.",
        "web.item.drag_title": "Drag to reorder",
        "web.item.priority_high": "High priority",
        "web.item.priority_low": "Low priority",
        "web.item.remaining_of": "Remaining {remaining} of {quantity}",
        "web.item.for_recipient": "For: {name}",
        "web.item.store_fallback": "Store",
        "web.item.notice_shortage": "Reservation unchanged. Available: {available}.",
        "web.item.notice_refused": "Reservation unchanged.",
        "web.item.available_of": "Available: {available} of {quantity}",
        "web.item.reserved_status": "Reserved",
        "web.item.reserved_by_you": "Reserved by you ({count})",
        "web.item.bought_suffix": " · Purchased",
        "web.item.reserve_btn": "Reserve",
        "web.item.change_btn": "Update",
        "web.item.cancel_reservation_btn": "Cancel reservation",
        "web.item.mark_purchased_btn": "Purchased",
        "web.item.undo_purchase_btn": "Return to reserved",
        "web.item.requested_label": "Requested: {count}",
        "web.item.received_label": "Received: {count}",
        "web.item.remaining_label": "Remaining: {count}",
        "web.item.quantity_label": "Quantity: {count}",
        "web.item.open_in_store": "Open in store",
        "web.item.receipt_btn": "Received",
        "web.item.move_up": "Move up",
        "web.item.move_down": "Move down",
        "web.item.archive_btn": "Archive",
        "web.item.unavailable": "This wish is no longer available. Please refresh the page.",
        "web.item.quick_add_placeholder": "Paste a link or wish title...",
        "web.item.empty_title": "Wish title cannot be empty",
        "web.item.quantity_below_reserved": (
            "Cannot set quantity below the already received amount ({count} pcs.)."
        ),
        "web.item.edit_busy_error": (
            "The wish was busy, the edit was not saved, and it can be submitted again."
        ),
        "web.item.preview_fallback_hint": (
            'Enter the wish title manually or click "More details".'
        ),
        "web.item.preview_title_placeholder": "Enter gift title...",
        "web.item.preview_dismiss": "Close preview",
        "web.item.modal_edit_title": "Edit wish",
        "web.item.modal_new_title": "New wish",
        "web.item.field_title": "Gift title *",
        "web.item.field_title_placeholder": "e.g. Set of wine glasses",
        "web.item.field_link": "Store link",
        "web.item.field_price": "Estimated price",
        "web.item.field_currency": "Currency",
        "web.item.field_quantity": "Requested quantity (pcs.)",
        "web.item.decrease_qty": "Decrease quantity",
        "web.item.increase_qty": "Increase quantity",
        "web.item.locked_quantity_hint": (
            "ℹ️ Reserved by givers: {count} pcs. You cannot set a quantity lower than the "
            "reserved amount."
        ),
        "web.item.field_recipient": "Who is this gift for",
        "web.item.recipient_shared": "Shared gift (for everyone)",
        "web.item.field_recipient_manual": "Or enter recipient name manually",
        "web.item.field_recipient_placeholder": "e.g. Baby, Grandma",
        "web.item.field_description": "Description and notes",
        "web.item.field_description_placeholder": "Size, color, preferences...",
        "web.item.field_image_url": "Image URL",
        "web.item.image_preview_alt": "Preview",
        "web.item.field_priority": "Priority",
        "web.item.priority_opt_low": "Nice to have",
        "web.item.priority_opt_medium": "Normal",
        "web.item.priority_opt_high": "Really want",
        "web.item.field_category": "Category",
        "web.item.field_category_placeholder": "Gadgets, books, home...",
        "web.item.archive_inline_btn": "Archive",
        "web.item.archive_inline_confirm": (
            "Move this wish to the archive? If it is already reserved, existing reservations "
            "will be kept."
        ),
        "web.item.archive_modal_title": "Archive wish?",
        "web.item.archive_modal_body": (
            '"{title}" will be moved to the archive. You can restore it at any time, and '
            "existing reservations will be preserved."
        ),
        "web.item.archive_received_note": (
            "Only the unreceived portion will be archived: already received items will remain in "
            'the "Gifted" section.'
        ),
        "web.item.archive_gifter_warning": (
            "This wish is already reserved by a giver. After archiving, it will stay in the "
            "giver's reservations list, but new reservations will not be available."
        ),
        "web.item.archive_warn_checkbox": "Warn when archiving reserved wishes",
        "web.item.archived_wishlist_error": "This wishlist is archived and cannot be edited.",
        "web.item.resource_not_found": "Wish or wishlist is no longer available.",
        "web.item.invalid_numeric": "Invalid numeric value.",
        "web.item.invalid_priority": "Invalid priority value.",
        "web.receipt.modal_title": "Mark as received",
        "web.receipt.remaining_label": "Remaining: {count}",
        "web.receipt.quantity_label": "How many pieces received",
        "web.receipt.summary_many": "Will mark as received: {chosen} pcs. of {remaining} remaining",
        "web.receipt.summary_one": "Will mark as received: 1 pc.",
        "web.receipt.summary_template": (
            "Will mark as received: {chosen} pcs. of {remaining} remaining"
        ),
        "web.receipt.irreversible": "You can correct or undo this receipt later in Gifted.",
        "web.receipt.confirm_btn": "Mark received",
        "web.receipt.recorded_notice": 'Marked as received: {count} pcs. ("{title}")',
        "web.receipt.edit_btn": "Edit",
        "web.receipt.cancel_btn": "Undo",
        "web.receipt.edit_modal_title": "Correct receipt quantity",
        "web.receipt.edit_quantity_label": "How many pieces were received",
        "web.receipt.edit_max_label": "Maximum: {count}",
        "web.receipt.edit_date_note": "The original receipt date will be preserved.",
        "web.receipt.edit_confirm_btn": "Save changes",
        "web.receipt.corrected_notice": 'Receipt updated: {count} pcs. ("{title}")',
        "web.receipt.cancel_modal_title": "Undo gift receipt?",
        "web.receipt.cancel_confirm_body": (
            'Remove the receipt record of {count} pcs. for "{title}"? '
            "The unreceived units will become available again."
        ),
        "web.receipt.cancel_confirm_btn": "Yes, undo receipt",
        "web.receipt.cancelled_notice": 'Receipt undone ("{title}")',
        "web.receipt.generic_failure": "Could not save the receipt. Please try again.",
        "web.receipt.error.quantity_invalid": "Enter a whole number of at least 1.",
        "web.receipt.error.quantity_above_remaining": (
            "Cannot mark more than remaining. Remaining: {n}."
        ),
        "web.receipt.error.nothing_remaining": "This wish has already been fully received.",
        "web.receipt.error.wish_archived": "This wish is archived. Restore it to mark as received.",
        "web.receipt.error.wishlist_not_active": (
            "This wishlist is not active; receipts cannot be recorded."
        ),
        "web.receipt.error.forbidden": (
            "You do not have permission to mark items received in this wishlist."
        ),
        "web.receipt.error.not_found": "Wish not found. Please refresh the page.",
        "web.receipt.error.receipt_not_found": (
            "This receipt record was already removed. Please refresh the page."
        ),
        "web.receipt.error.busy": "Could not save the receipt right now. Please try again.",
        "web.share.modal_title": "Share wishlist",
        "web.share.public_link_label": "Public link for givers",
        "web.share.public_link_hint": (
            "Givers can view the wishlist and reserve gifts secretly from you."
        ),
        "web.share.invite_link_label": "Invite link for co-authors",
        "web.share.invite_link_hint": "Co-authors can add and edit wishes in this list.",
        "web.share.regenerate_invite": "Revoke and create new link",
        "web.share.owner_fallback": "List owner",
        "web.share.role_owner": "Owner",
        "web.share.role_admin": "Admin",
        "web.share.role_member": "Member",
        "web.share.member_id": "Member ID: {user_id}",
        "web.invite.page_title_valid": "Invitation to {title} — Wishenka",
        "web.invite.page_title_error": "Invitation error — Wishenka",
        "web.invite.unavailable_heading": "Invitation unavailable",
        "web.invite.invalid_or_expired": "The invitation link is invalid or has expired.",
        "web.invite.go_home": "Back to home",
        "web.invite.invited_by": "{owner} invites you to become a co-author of this wishlist.",
        "web.invite.join_btn": "Join wishlist",
        "web.invite.join_success": "You have successfully joined the wishlist!",
        "web.reservations.title": "My reservations",
        "web.reservations.status_booked": "Reserved",
        "web.reservations.status_bought": "Purchased",
        "web.reservations.empty": "No reservations",
        "web.reservations.wish_received": "Wish received by owner",
        "web.reservations.complete": "Gift delivered",
        "web.reservations.completed": "Promise completed.",
        "web.reservations.for_recipient": "For: {name}",
        "web.reservations.wish_archived": "Wish is archived",
        "web.reservations.list_archived": "Wishlist is archived",
        "web.reservations.go_to_wish": "Go to wish",
        "web.rate_limit.title": "Too many requests",
        "web.rate_limit.message": (
            "Too many requests. Please wait {seconds} seconds and try again."
        ),
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
        "settings.saving": "Сохраняем…",
        "settings.rejected": "Не сохранено. Прежнее значение сохранено; повторите попытку.",
        "settings.not_saved_after_error": (
            "Не сохранено: запрос не удался. Текущее значение проверено и не изменилось."
        ),
        "settings.confirmed_after_error": (
            "Сервер сообщил об ошибке, но новое значение проверено и действует."
        ),
        "settings.refreshed": "Текущее значение проверено и показано.",
        "settings.unknown_state": (
            "Не удалось подтвердить текущее значение. Нажмите «Повторить», чтобы проверить снова."
        ),
        "settings.retry": "Повторить",
        "settings.reload": "Перезагрузить страницу",
        "settings.locale_reload_needed": (
            "Язык изменён на сервере. Перезагрузите страницу, чтобы применить его."
        ),
        "settings.birthdate_current_label": "Текущая дата рождения:",
        "settings.birthdate_priority_hint": (
            "Год необязателен. Сохранённая здесь дата не будет перезаписана данными Telegram."
        ),
        "settings.precedence_hint": (
            "Это значения по умолчанию. Выбор для отдельного вишлиста ниже имеет приоритет; "
            "«Как в общих» следует этим значениям."
        ),
        "settings.delete_preview_failed": (
            "Не удалось загрузить сводку удаления. Повторите попытку."
        ),
        "settings.delete_unknown": (
            "Результат удаления неизвестен. Перезагрузите страницу, чтобы проверить аккаунт."
        ),
        "settings.deleting": "Удаляем…",
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
        "notices.receipt_reverted": (
            "Отметка о получении желания «{wish}» из списка «{wishlist}» "
            "была отменена или скорректирована.\n"
            "Проверьте свою бронь и при необходимости оставьте или измените её."
        ),
        "notices.item_quantity_overbooked": (
            "Требуемое количество для желания «{wish}» из списка «{wishlist}» уменьшилось.\n"
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
        "miniapp.home.lead": "Ваши списки, совместные планы и избранное в одном месте.",
        "miniapp.home.create_wishlist": "Создать вишлист",
        "miniapp.home.create_failed": "Не удалось создать вишлист. Попробуйте ещё раз.",
        "miniapp.home.viewing_history": "История просмотров",
        "miniapp.home.reservations_hint": "Активные и купленные обещания подарков",
        "miniapp.home.my_wishlists": "Мои вишлисты",
        "miniapp.home.my_wishlists_sub": "Списки, которые вы создали и ведёте",
        "miniapp.home.my_wishlists_empty": "Пока нет личных вишлистов",
        "miniapp.home.my_wishlists_empty_hint": (
            "Нажмите «Создать вишлист» выше, чтобы собрать свой первый список."
        ),
        "miniapp.home.collaborating": "Совместные",
        "miniapp.home.collaborating_sub": (
            "Общие списки, где вы участвуете как администратор или соавтор"
        ),
        "miniapp.home.collaborating_empty": "Пока нет совместных вишлистов",
        "miniapp.home.collaborating_empty_hint": (
            "Попросите владельца списка прислать ссылку-приглашение для совместного ведения."
        ),
        "miniapp.home.favorites": "Избранные",
        "miniapp.home.favorites_sub": (
            "Сохранённые вишлисты друзей и близких для быстрого доступа"
        ),
        "miniapp.home.favorites_empty": "Пока нет избранных вишлистов",
        "miniapp.home.favorites_empty_hint": (
            "Откройте чужой вишлист по публичной ссылке и добавьте его в избранное."
        ),
        "miniapp.home.deleted_sub": (
            "Списки, которые можно восстановить до окончания срока хранения"
        ),
        "miniapp.home.open_wishlist": "Открыть",
        "miniapp.home.open_wishlist_named": "Открыть «{name}»",
        "miniapp.home.remove": "Удалить",
        "miniapp.home.remove_favorite": "Убрать из избранного",
        "miniapp.home.remove_favorite_named": "Убрать из избранного «{name}»",
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
        "miniapp.share.public_hint": (
            "Гости могут посмотреть желания и тайно забронировать подарки, но не менять список."
        ),
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
        "miniapp.wishlist_settings.subtitle": "Измените данные этого вишлиста.",
        "miniapp.wishlist_settings.hint_title": "Название, по которому узнают вишлист.",
        "miniapp.wishlist_settings.hint_description": "Добавьте подробности для гостей.",
        "miniapp.wishlist_settings.hint_event": "Название события, необязательно.",
        "miniapp.wishlist_settings.hint_date": "Дата и время события, необязательно.",
        "miniapp.wishlist_settings.cancelled": "Изменения отменены",
        "miniapp.wishlist_settings.field_title": "Название",
        "miniapp.wishlist_settings.field_description": "Описание",
        "miniapp.wishlist_settings.field_event": "Событие",
        "miniapp.wishlist_settings.field_date": "Дата",
        "miniapp.wishlist_settings.save": "Сохранить настройки",
        "miniapp.wishlist_settings.cancel": "Отмена",
        "miniapp.wishlist_settings.saved": "Настройки сохранены",
        "miniapp.wishlist_settings.saved_refresh_failed": (
            "Настройки сохранены, но обновить вишлист не удалось"
        ),
        "miniapp.wishlist_settings.save_failed": (
            "Не удалось сохранить настройки. Ваши изменения сохранены в форме."
        ),
        "miniapp.members.heading": "Управление участниками",
        "miniapp.members.subtitle": (
            "Владелец и администраторы управляют списком, соавторы добавляют желания."
        ),
        "miniapp.members.invite_hint": "По этой ссылке соавтор может добавлять и менять желания.",
        "miniapp.members.role_updated": "Роль участника изменена",
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
        "miniapp.list.occasion_prefix": "Событие:",
        "miniapp.list.wishes_subtitle": "Желания в этом списке.",
        "miniapp.list.wishes_empty": "Пока нет желаний.",
        "miniapp.list.restored": "Вишлист восстановлен",
        "miniapp.list.wishes_future_update": "Добавление желаний появится в следующем обновлении.",
        "miniapp.list.archived_notice": "Этот вишлист в архиве и доступен только для чтения.",
        "miniapp.list.restore": "Восстановить вишлист",
        "miniapp.list.restore_failed": "Не удалось восстановить вишлист",
        "miniapp.list.load_failed": "Не удалось загрузить этот вишлист",
        "miniapp.list.refresh_unavailable": "Вишлист временно недоступен",
        "miniapp.list.refresh_retry": "Попробовать снова",
        "miniapp.list.changed_refresh_failed": (
            "Изменение сохранено, но обновить вишлист не удалось"
        ),
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
        # SSR web pages, partials, and UI routes
        "web.common.request_prepare_error": "Не удалось подготовить запрос. Повторите попытку.",
        "web.common.wish_busy_error": ("Желание занято, бронь не изменилась. Повторите попытку."),
        "web.common.member_fallback": "Участник #{id}",
        "web.common.owner_suffix": "{name} (Владелец)",
        "web.common.cancel": "Отмена",
        "web.common.close": "Закрыть",
        "web.common.save": "Сохранить",
        "web.common.delete": "Удалить",
        "web.common.edit": "Редактировать",
        "web.common.add": "Добавить",
        "web.common.details": "Подробнее",
        "web.wishlist.author": "Автор:",
        "web.wishlist.empty": "В этом списке желаний пока нет подарков.",
        "web.wishlist.list_changed": "Список изменился. Обновляем.",
        "web.wishlist.archived_heading": "Архив желаний ({count})",
        "web.wishlist.archived_remaining": "Осталось {count}",
        "web.wishlist.restore": "Восстановить",
        "web.wishlist.gifted_heading": "Подаренные ({count})",
        "web.wishlist.gifted_load_error": "Не удалось загрузить «Подаренные». Обновите страницу.",
        "web.wishlist.gifted_for": "Для: {name}",
        "web.wishlist.gifted_received_of": "Получено: {received} из {requested}",
        "web.wishlist.gifted_approx_date": "≈ {day} (дата примерная)",
        "web.wishlist.gifted_act_qty": "{quantity} шт.",
        "web.item.drag_title": "Перетащить",
        "web.item.priority_high": "Высокий приоритет",
        "web.item.priority_low": "Низкий приоритет",
        "web.item.remaining_of": "Осталось {remaining} из {quantity}",
        "web.item.for_recipient": "Для: {name}",
        "web.item.store_fallback": "Магазин",
        "web.item.notice_shortage": "Бронь не изменилась. Свободно: {available}.",
        "web.item.notice_refused": "Бронь не изменилась.",
        "web.item.available_of": "Доступно: {available} из {quantity}",
        "web.item.reserved_status": "Забронировано",
        "web.item.reserved_by_you": "Забронировано вами ({count})",
        "web.item.bought_suffix": " · Куплено",
        "web.item.reserve_btn": "Забронировать",
        "web.item.change_btn": "Изменить",
        "web.item.cancel_reservation_btn": "Отменить бронь",
        "web.item.mark_purchased_btn": "Куплено",
        "web.item.undo_purchase_btn": "Вернуть в бронь",
        "web.item.requested_label": "Запрошено: {count}",
        "web.item.received_label": "Получено: {count}",
        "web.item.remaining_label": "Осталось: {count}",
        "web.item.quantity_label": "Количество: {count}",
        "web.item.open_in_store": "Открыть в магазине",
        "web.item.receipt_btn": "Получено",
        "web.item.move_up": "Переместить выше",
        "web.item.move_down": "Переместить ниже",
        "web.item.archive_btn": "Архивировать",
        "web.item.unavailable": "Желание больше недоступно. Обновите страницу.",
        "web.item.quick_add_placeholder": "Вставьте ссылку или название желания...",
        "web.item.empty_title": "Название желания не может быть пустым",
        "web.item.quantity_below_reserved": (
            "Нельзя указать количество меньше уже полученного ({count} шт.)."
        ),
        "web.item.edit_busy_error": (
            "Желание было занято, изменения не сохранены — попробуйте отправить снова."
        ),
        "web.item.preview_fallback_hint": (
            "Заполните название желания вручную или нажмите «Подробнее»."
        ),
        "web.item.preview_title_placeholder": "Введите название подарка...",
        "web.item.preview_dismiss": "Закрыть предпросмотр",
        "web.item.modal_edit_title": "Редактировать желание",
        "web.item.modal_new_title": "Новое желание",
        "web.item.field_title": "Название подарка *",
        "web.item.field_title_placeholder": "Например: Набор винных бокалов",
        "web.item.field_link": "Ссылка на магазин",
        "web.item.field_price": "Ориентировочная цена",
        "web.item.field_currency": "Валюта",
        "web.item.field_quantity": "Требуемое количество (шт.)",
        "web.item.decrease_qty": "Уменьшить количество",
        "web.item.increase_qty": "Увеличить количество",
        "web.item.locked_quantity_hint": (
            "ℹ️ Забронировано дарителями: {count} шт. Нельзя указать меньше забронированного объема."
        ),
        "web.item.field_recipient": "Кому предназначен подарок",
        "web.item.recipient_shared": "Общий подарок (для всех)",
        "web.item.field_recipient_manual": "Или укажите имя получателя вручную",
        "web.item.field_recipient_placeholder": "Например: Малыш, Бабушка",
        "web.item.field_description": "Описание и комментарий",
        "web.item.field_description_placeholder": "Размер, цвет, пожелания...",
        "web.item.field_image_url": "Ссылка на изображение",
        "web.item.image_preview_alt": "Предпросмотр",
        "web.item.field_priority": "Приоритет",
        "web.item.priority_opt_low": "Если останется",
        "web.item.priority_opt_medium": "Обычный",
        "web.item.priority_opt_high": "Очень хочется",
        "web.item.field_category": "Категория",
        "web.item.field_category_placeholder": "Гаджеты, книги, дом...",
        "web.item.archive_inline_btn": "В архив",
        "web.item.archive_inline_confirm": (
            "Перенести желание в архив? Если подарок уже забронирован, бронирования дарителей "
            "сохранятся."
        ),
        "web.item.archive_modal_title": "Архивировать желание?",
        "web.item.archive_modal_body": (
            "«{title}» будет перемещено в архив. Его можно восстановить в любой момент, а "
            "существующие брони сохранятся."
        ),
        "web.item.archive_received_note": (
            "Архивируется только неполученная часть: полученные штуки останутся в разделе "
            "«Подаренные»."
        ),
        "web.item.archive_gifter_warning": (
            "Это желание уже зарезервировано дарителем. После архивации оно останется в списке "
            "брони дарителя, но новые брони будут недоступны."
        ),
        "web.item.archive_warn_checkbox": "Предупреждать при архивации зарезервированных желаний",
        "web.item.archived_wishlist_error": "Вишлист в архиве — изменения недоступны.",
        "web.item.resource_not_found": "Желание или вишлист больше недоступны.",
        "web.item.invalid_numeric": "Некорректное числовое значение.",
        "web.item.invalid_priority": "Некорректный приоритет.",
        "web.receipt.modal_title": "Отметить получение",
        "web.receipt.remaining_label": "Осталось: {count}",
        "web.receipt.quantity_label": "Сколько штук получено",
        "web.receipt.summary_many": (
            "Будет отмечено получено: {chosen} шт. из {remaining} оставшихся"
        ),
        "web.receipt.summary_one": "Будет отмечено получено: 1 шт.",
        "web.receipt.summary_template": (
            "Будет отмечено получено: {chosen} шт. из {remaining} оставшихся"
        ),
        "web.receipt.irreversible": (
            "Ошибку можно будет исправить или отменить в разделе «Подаренные»."
        ),
        "web.receipt.confirm_btn": "Отметить полученным",
        "web.receipt.recorded_notice": "Отмечено получено: {count} шт. («{title}»)",
        "web.receipt.edit_btn": "Изменить",
        "web.receipt.cancel_btn": "Отменить",
        "web.receipt.edit_modal_title": "Исправить количество",
        "web.receipt.edit_quantity_label": "Сколько штук получено",
        "web.receipt.edit_max_label": "Максимум: {count}",
        "web.receipt.edit_date_note": "Исходная дата получения сохранится.",
        "web.receipt.edit_confirm_btn": "Сохранить",
        "web.receipt.corrected_notice": "Количество обновлено: {count} шт. («{title}»)",
        "web.receipt.cancel_modal_title": "Отменить отметку о получении?",
        "web.receipt.cancel_confirm_body": (
            "Удалить запись о получении ({count} шт.) для «{title}»? "
            "Неполученные штуки снова станут доступны."
        ),
        "web.receipt.cancel_confirm_btn": "Да, отменить",
        "web.receipt.cancelled_notice": "Отметка о получении отменена («{title}»)",
        "web.receipt.generic_failure": "Не удалось сохранить отметку. Повторите попытку.",
        "web.receipt.error.quantity_invalid": "Укажите целое число не меньше 1.",
        "web.receipt.error.quantity_above_remaining": (
            "Нельзя отметить больше, чем осталось. Осталось: {n}."
        ),
        "web.receipt.error.nothing_remaining": "Это желание уже полностью получено.",
        "web.receipt.error.wish_archived": (
            "Желание в архиве. Восстановите его, чтобы отметить получение."
        ),
        "web.receipt.error.wishlist_not_active": "Вишлист не активен, отметить получение нельзя.",
        "web.receipt.error.forbidden": "У вас нет права отмечать получение в этом вишлисте.",
        "web.receipt.error.not_found": "Желание не найдено. Обновите страницу.",
        "web.receipt.error.receipt_not_found": (
            "Эта запись о получении уже удалена. Обновите страницу."
        ),
        "web.receipt.error.busy": "Не удалось сохранить отметку сейчас. Повторите попытку.",
        "web.share.modal_title": "Поделиться списком",
        "web.share.public_link_label": "Публичная ссылка для дарителей",
        "web.share.public_link_hint": (
            "Дарители увидят список желаний и смогут бронировать подарки втайне от вас."
        ),
        "web.share.invite_link_label": "Ссылка-приглашение для соавторов",
        "web.share.invite_link_hint": (
            "Соавторы смогут добавлять и редактировать желания в этом списке."
        ),
        "web.share.regenerate_invite": "Отозвать и создать новую ссылку",
        "web.share.owner_fallback": "Владелец списка",
        "web.share.role_owner": "Владелец",
        "web.share.role_admin": "Администратор",
        "web.share.role_member": "Участник",
        "web.share.member_id": "Участник ID: {user_id}",
        "web.invite.page_title_valid": "Приглашение в {title} — Wishenka",
        "web.invite.page_title_error": "Ошибка приглашения — Wishenka",
        "web.invite.unavailable_heading": "Приглашение недоступно",
        "web.invite.invalid_or_expired": (
            "Ссылка приглашения недействительна или истек срок действия."
        ),
        "web.invite.go_home": "На главную",
        "web.invite.invited_by": (
            "Пользователь {owner} приглашает вас стать соавтором этого списка желаний."
        ),
        "web.invite.join_btn": "Присоединиться к списку",
        "web.invite.join_success": "Вы успешно присоединились к вишлисту!",
        "web.reservations.title": "Мои бронирования",
        "web.reservations.status_booked": "Забронировано",
        "web.reservations.status_bought": "Куплено",
        "web.reservations.empty": "Нет бронирований",
        "web.reservations.wish_received": "Желание получено владельцем",
        "web.reservations.complete": "Подарок вручён",
        "web.reservations.completed": "Обещание завершено.",
        "web.reservations.for_recipient": "Для: {name}",
        "web.reservations.wish_archived": "Желание в архиве",
        "web.reservations.list_archived": "Вишлист в архиве",
        "web.reservations.go_to_wish": "К желанию",
        "web.rate_limit.title": "Слишком много запросов",
        "web.rate_limit.message": (
            "Слишком много запросов. Пожалуйста, подождите {seconds} сек. и повторите попытку."
        ),
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
