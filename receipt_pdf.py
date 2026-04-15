from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

import qrcode
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps


PAGE_WIDTH = 1240
PAGE_HEIGHT = 1754
PAGE_MARGIN_X = 88
PAGE_MARGIN_Y = 84
PAGE_BOTTOM = PAGE_HEIGHT - PAGE_MARGIN_Y
CONTENT_WIDTH = PAGE_WIDTH - (PAGE_MARGIN_X * 2)
CARD_RADIUS = 34
CARD_PADDING = 34
CARD_GAP = 26

COLOR_PAGE = (250, 244, 236)
COLOR_CARD = (255, 251, 246)
COLOR_BORDER = (224, 203, 184)
COLOR_HEADER = (45, 28, 22)
COLOR_ACCENT = (225, 116, 47)
COLOR_GOLD = (236, 196, 92)
COLOR_TEXT = (45, 34, 29)
COLOR_MUTED = (108, 88, 78)
COLOR_TEAL = (59, 110, 111)
COLOR_LIGHT_ACCENT = (252, 238, 227)

BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "static" / "images" / "mcq-logo.jpg"

FONT_REGULAR_CANDIDATES = (
    "Arial.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)
FONT_BOLD_CANDIDATES = (
    "Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)


@lru_cache(maxsize=None)
def _load_font(size: int, bold: bool = False):
    candidates = FONT_BOLD_CANDIDATES if bold else FONT_REGULAR_CANDIDATES
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _text_size(font, text: str) -> tuple[int, int]:
    sample = text or " "
    left, top, right, bottom = font.getbbox(sample)
    return right - left, bottom - top


def _line_height(font, extra: int = 0) -> int:
    return _text_size(font, "Ag")[1] + extra


def _split_token(token: str, font, max_width: int) -> list[str]:
    if _text_size(font, token)[0] <= max_width:
        return [token]

    chunks: list[str] = []
    current = ""
    for char in token:
        candidate = f"{current}{char}"
        if current and _text_size(font, candidate)[0] > max_width:
            chunks.append(current)
            current = char
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [token]


def _wrap_text(text: str, font, max_width: int) -> list[str]:
    paragraphs = (text or "").splitlines() or [""]
    lines: list[str] = []
    for paragraph in paragraphs:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            pieces = _split_token(word, font, max_width)
            for piece in pieces:
                candidate = piece if not current else f"{current} {piece}"
                if current and _text_size(font, candidate)[0] > max_width:
                    lines.append(current)
                    current = piece
                else:
                    current = candidate
        if current:
            lines.append(current)
    return lines or [""]


def _rounded_rect(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill, outline=None, width: int = 2) -> None:
    draw.rounded_rectangle(box, radius=CARD_RADIUS, fill=fill, outline=outline, width=width)


def _fit_logo(max_width: int, max_height: int) -> Image.Image | None:
    if not LOGO_PATH.exists():
        return None
    logo = Image.open(LOGO_PATH).convert("RGBA")
    diff = ImageChops.difference(logo.convert("RGB"), Image.new("RGB", logo.size, "white"))
    bbox = diff.getbbox()
    if bbox:
        logo = logo.crop(bbox)
    logo.thumbnail((max_width, max_height), Image.LANCZOS)
    return logo


def _build_qr(order: dict, size: int = 220) -> Image.Image:
    queue_text = f"\nqueue_number={order.get('queue_number')}" if order.get("queue_number") else ""
    counter_text = f"\ncounter_label={order.get('counter_label')}" if order.get("counter_label") else ""
    qr = qrcode.QRCode(
        version=3,
        border=1,
        box_size=10,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    qr.add_data(
        f"MCQ ORDER\norder_number={order['order_number']}\nconfirmation_code={order['confirmation_code']}\n"
        f"fulfillment_type={order['fulfillment_type']}\npickup_at={order['pickup_at']}{queue_text}{counter_text}"
    )
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return image.resize((size, size), Image.NEAREST)


class ReceiptPdfRenderer:
    def __init__(self, order: dict):
        self.order = order
        self.logo = _fit_logo(250, 128)
        self.qr = _build_qr(order)
        self.pages: list[Image.Image] = []
        self.page: Image.Image | None = None
        self.draw: ImageDraw.ImageDraw | None = None
        self.cursor_y = PAGE_MARGIN_Y
        self.page_number = 0

        self.font_label = _load_font(22, bold=True)
        self.font_section = _load_font(32, bold=True)
        self.font_title = _load_font(50, bold=True)
        self.font_header_title = _load_font(42, bold=True)
        self.font_huge = _load_font(62, bold=True)
        self.font_ticket_value = _load_font(54, bold=True)
        self.font_body = _load_font(26)
        self.font_body_bold = _load_font(28, bold=True)
        self.font_small = _load_font(22)
        self.font_small_bold = _load_font(22, bold=True)

    def build(self) -> bytes:
        self._new_page(first_page=True)
        self._draw_ticket_card()
        self._draw_two_info_cards()
        self._draw_items_card()
        self._draw_summary_card()
        self._draw_notes_card()
        self._draw_notifications_card()
        self._draw_footer_note()

        rgb_pages = [page.convert("RGB") for page in self.pages]
        buffer = io.BytesIO()
        rgb_pages[0].save(
            buffer,
            format="PDF",
            resolution=150.0,
            save_all=True,
            append_images=rgb_pages[1:],
        )
        return buffer.getvalue()

    def _new_page(self, *, first_page: bool) -> None:
        self.page = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), COLOR_PAGE)
        self.draw = ImageDraw.Draw(self.page)
        self.pages.append(self.page)
        self.page_number += 1

        header_top = 34
        header_height = 232 if first_page else 144
        header_box = (PAGE_MARGIN_X, header_top, PAGE_WIDTH - PAGE_MARGIN_X, header_top + header_height)
        _rounded_rect(self.draw, header_box, COLOR_HEADER)

        if self.logo:
            logo_wrap = (PAGE_MARGIN_X + 26, header_top + 24, PAGE_MARGIN_X + 242, header_top + 172)
            _rounded_rect(self.draw, logo_wrap, (255, 251, 246))
            logo_x = logo_wrap[0] + ((logo_wrap[2] - logo_wrap[0] - self.logo.width) // 2)
            logo_y = logo_wrap[1] + ((logo_wrap[3] - logo_wrap[1] - self.logo.height) // 2)
            self.page.paste(self.logo, (logo_x, logo_y), self.logo)

        text_x = PAGE_MARGIN_X + 272
        detail_x = PAGE_WIDTH - PAGE_MARGIN_X - 248
        title_y = header_top + 32
        title_width = detail_x - text_x - 28
        for line in _wrap_text("MCQ Vietnamese Street Food", self.font_header_title, title_width):
            self.draw.text((text_x, title_y), line, font=self.font_header_title, fill=(255, 247, 239))
            title_y += _line_height(self.font_header_title, 6)
        subtitle = "Queue pickup receipt" if self.order.get("is_instant") else "Scheduled pickup receipt"
        for line in _wrap_text(subtitle, self.font_body_bold, title_width):
            self.draw.text((text_x, title_y + 2), line, font=self.font_body_bold, fill=(255, 222, 160))
            title_y += _line_height(self.font_body_bold, 6)

        detail_y = header_top + 42
        order_chip = (
            f"Queue {self.order.get('queue_display')}"
            if self.order.get("is_instant")
            else self.order.get("pickup_time", "")
        )
        chip_box = (detail_x, detail_y, PAGE_WIDTH - PAGE_MARGIN_X - 26, detail_y + 54)
        _rounded_rect(self.draw, chip_box, (82, 58, 46))
        self._draw_centered_text(chip_box, order_chip, self.font_small_bold, (255, 239, 205))
        meta_y = detail_y + 78
        meta_width = chip_box[2] - chip_box[0]
        for block, font, fill in (
            (f"Order {self.order['order_number']}", self.font_body_bold, (255, 247, 239)),
            (f"Confirmation {self.order['confirmation_code']}", self.font_small, (230, 213, 201)),
            (f"Updated {self.order['updated_at']}", self.font_small, (230, 213, 201)),
        ):
            for line in _wrap_text(block, font, meta_width):
                self.draw.text((detail_x, meta_y), line, font=font, fill=fill)
                meta_y += _line_height(font, 4)
            meta_y += 6

        self.cursor_y = header_box[3] + 34

    def _draw_centered_text(self, box: tuple[int, int, int, int], text: str, font, fill) -> None:
        width, height = _text_size(font, text)
        x = box[0] + ((box[2] - box[0] - width) // 2)
        y = box[1] + ((box[3] - box[1] - height) // 2) - 2
        self.draw.text((x, y), text, font=font, fill=fill)

    def _ensure_space(self, height: int) -> None:
        if self.cursor_y + height <= PAGE_BOTTOM:
            return
        self._new_page(first_page=False)

    def _card_box(self, height: int) -> tuple[int, int, int, int]:
        self._ensure_space(height)
        box = (PAGE_MARGIN_X, self.cursor_y, PAGE_WIDTH - PAGE_MARGIN_X, self.cursor_y + height)
        self.cursor_y = box[3] + CARD_GAP
        return box

    def _draw_card_background(self, box: tuple[int, int, int, int], fill=COLOR_CARD) -> None:
        _rounded_rect(self.draw, box, fill, outline=COLOR_BORDER)

    def _draw_card_heading(self, x: int, y: int, title: str, subtitle: str | None = None) -> int:
        self.draw.text((x, y), title, font=self.font_section, fill=COLOR_TEXT)
        y += _line_height(self.font_section, 8)
        if subtitle:
            for line in _wrap_text(subtitle, self.font_body, CONTENT_WIDTH - (CARD_PADDING * 2)):
                self.draw.text((x, y), line, font=self.font_body, fill=COLOR_MUTED)
                y += _line_height(self.font_body, 8)
        return y + 6

    def _draw_ticket_card(self) -> None:
        text_width = CONTENT_WIDTH - 300 - (CARD_PADDING * 2) - 24
        summary_font = self.font_body
        summary_line_height = _line_height(summary_font, 8)
        hero_value = (
            f"{self.order['queue_display']} at {self.order['counter_label']}"
            if self.order.get("is_instant")
            else f"{self.order['pickup_day']} at {self.order['pickup_time']}"
        )
        hero_lines = _wrap_text(hero_value, self.font_ticket_value, text_width)
        summary_lines = _wrap_text(self.order["fulfillment_summary"], summary_font, text_width)
        hero_height = len(hero_lines) * _line_height(self.font_ticket_value, 8)
        base_height = 84 + hero_height + (len(summary_lines) * summary_line_height) + 208
        card_height = max(332, base_height)
        box = self._card_box(card_height)
        self._draw_card_background(box)

        x = box[0] + CARD_PADDING
        y = box[1] + CARD_PADDING
        label = "Instant online order" if self.order.get("is_instant") else "Scheduled pickup"
        self.draw.text((x, y), label.upper(), font=self.font_label, fill=COLOR_ACCENT)
        y += _line_height(self.font_label, 4)
        for line in hero_lines:
            self.draw.text((x, y), line, font=self.font_ticket_value, fill=COLOR_TEXT)
            y += _line_height(self.font_ticket_value, 8)
        y += 6
        for line in summary_lines:
            self.draw.text((x, y), line, font=summary_font, fill=COLOR_MUTED)
            y += summary_line_height

        info_rows = [
            ("Status", f"{self.order['order_status']} and payment {self.order['payment_status']}"),
            ("Placed", self.order["created_at"]),
            ("Customer", f"{self.order['customer_name']} · {self.order['customer_phone']}"),
        ]
        if self.order.get("quoted_wait_display"):
            info_rows.append(("Quoted wait", self.order["quoted_wait_display"]))

        y += 14
        label_gap = _line_height(self.font_small_bold, 4)
        body_gap = _line_height(self.font_small, 8)
        for title, value in info_rows:
            self.draw.text((x, y), title.upper(), font=self.font_small_bold, fill=COLOR_TEAL)
            y += label_gap
            for line in _wrap_text(value, self.font_small, text_width):
                self.draw.text((x, y), line, font=self.font_small, fill=COLOR_TEXT)
                y += body_gap
            y += 10

        qr_size = 220
        qr_box = (box[2] - CARD_PADDING - qr_size, box[1] + CARD_PADDING, box[2] - CARD_PADDING, box[1] + CARD_PADDING + qr_size)
        _rounded_rect(self.draw, qr_box, (255, 255, 255), outline=COLOR_BORDER)
        qr_x = qr_box[0] + ((qr_size - self.qr.width) // 2)
        qr_y = qr_box[1] + ((qr_size - self.qr.height) // 2)
        self.page.paste(self.qr, (qr_x, qr_y))
        qr_label_y = qr_box[3] + 16
        self.draw.text((qr_box[0], qr_label_y), "SCAN FOR VERIFICATION", font=self.font_small_bold, fill=COLOR_ACCENT)
        qr_copy = _wrap_text(f"Order {self.order['order_number']} · Confirmation {self.order['confirmation_code']}", self.font_small, qr_size)
        qr_copy_y = qr_label_y + _line_height(self.font_small_bold, 4)
        for line in qr_copy:
            self.draw.text((qr_box[0], qr_copy_y), line, font=self.font_small, fill=COLOR_MUTED)
            qr_copy_y += _line_height(self.font_small, 6)

    def _estimate_info_card_height(self, width: int, title: str, rows: list[tuple[str, str]]) -> int:
        inner_width = width - (CARD_PADDING * 2)
        value_width = inner_width
        height = CARD_PADDING + _line_height(self.font_section, 10)
        for row_title, row_value in rows:
            height += _line_height(self.font_small_bold, 4)
            height += len(_wrap_text(row_value, self.font_body, value_width)) * _line_height(self.font_body, 8)
            height += 12
        return max(220, height + CARD_PADDING)

    def _draw_info_card(self, box: tuple[int, int, int, int], title: str, rows: list[tuple[str, str]]) -> None:
        self._draw_card_background(box)
        x = box[0] + CARD_PADDING
        y = box[1] + CARD_PADDING
        y = self._draw_card_heading(x, y, title)
        width = box[2] - box[0] - (CARD_PADDING * 2)
        for index, (row_title, row_value) in enumerate(rows):
            if index:
                self.draw.line((x, y, box[2] - CARD_PADDING, y), fill=COLOR_BORDER, width=2)
                y += 16
            self.draw.text((x, y), row_title.upper(), font=self.font_small_bold, fill=COLOR_ACCENT)
            y += _line_height(self.font_small_bold, 4)
            for line in _wrap_text(row_value, self.font_body, width):
                self.draw.text((x, y), line, font=self.font_body, fill=COLOR_TEXT)
                y += _line_height(self.font_body, 8)
            y += 10

    def _draw_two_info_cards(self) -> None:
        gap = 24
        column_width = (CONTENT_WIDTH - gap) // 2
        customer_rows = [
            ("Name", self.order["customer_name"]),
            ("Email", self.order["customer_email"]),
            ("Phone", self.order["customer_phone"]),
        ]
        payment_rows = [
            ("Reference", self.order["payment_reference"]),
            ("Method", self.order["payment_method"]),
            ("Status", self.order["payment_status"]),
        ]
        if self.order.get("card_last4"):
            payment_rows.append(("Card ending", self.order["card_last4"]))
        if self.order.get("latest_payment_attempt"):
            payment_rows.append(("Attempt log", self.order["latest_payment_attempt"]["reference"]))

        left_height = self._estimate_info_card_height(column_width, "Customer details", customer_rows)
        right_height = self._estimate_info_card_height(column_width, "Payment log", payment_rows)
        box_height = max(left_height, right_height)
        self._ensure_space(box_height)

        top = self.cursor_y
        left_box = (PAGE_MARGIN_X, top, PAGE_MARGIN_X + column_width, top + box_height)
        right_box = (left_box[2] + gap, top, left_box[2] + gap + column_width, top + box_height)
        self._draw_info_card(left_box, "Customer details", customer_rows)
        self._draw_info_card(right_box, "Payment log", payment_rows)
        self.cursor_y = top + box_height + CARD_GAP

    def _item_row_height(self, title: str, detail: str, price_width: int, left_width: int) -> int:
        title_lines = _wrap_text(title, self.font_body_bold, left_width)
        detail_lines = _wrap_text(detail, self.font_small, left_width)
        height = 18
        height += len(title_lines) * _line_height(self.font_body_bold, 4)
        height += len(detail_lines) * _line_height(self.font_small, 6)
        return max(height, _line_height(self.font_body_bold, 8) * 2)

    def _draw_items_card(self) -> None:
        price_width = 180
        left_width = CONTENT_WIDTH - (CARD_PADDING * 2) - price_width - 24
        items = [
            (
                f"{line['quantity']} x {line['name']}",
                f"{line['unit_price_display']} each · {line['category']}",
                line["line_total_display"],
            )
            for line in self.order["lines"]
        ]

        index = 0
        continuation = False
        while index < len(items):
            min_chunk_height = 260
            self._ensure_space(min_chunk_height)
            top = self.cursor_y
            available = PAGE_BOTTOM - top
            chunk: list[tuple[str, str, str]] = []
            used = CARD_PADDING + _line_height(self.font_section, 12) + 18
            while index < len(items):
                title, detail, _amount = items[index]
                row_height = self._item_row_height(title, detail, price_width, left_width) + 18
                if chunk and used + row_height + CARD_PADDING > available:
                    break
                if not chunk and used + row_height + CARD_PADDING > available:
                    self._new_page(first_page=False)
                    top = self.cursor_y
                    available = PAGE_BOTTOM - top
                    used = CARD_PADDING + _line_height(self.font_section, 12) + 18
                chunk.append(items[index])
                used += row_height
                index += 1

            box = (PAGE_MARGIN_X, top, PAGE_WIDTH - PAGE_MARGIN_X, top + used + CARD_PADDING)
            self._draw_card_background(box)
            x = box[0] + CARD_PADDING
            y = box[1] + CARD_PADDING
            title = "Order items" if not continuation else "Order items (continued)"
            subtitle = "Saved exactly as charged at checkout."
            y = self._draw_card_heading(x, y, title, subtitle)
            self.draw.line((x, y, box[2] - CARD_PADDING, y), fill=COLOR_BORDER, width=2)
            y += 18

            for row_index, (row_title, row_detail, row_amount) in enumerate(chunk):
                if row_index:
                    self.draw.line((x, y, box[2] - CARD_PADDING, y), fill=COLOR_BORDER, width=1)
                    y += 18
                title_lines = _wrap_text(row_title, self.font_body_bold, left_width)
                detail_lines = _wrap_text(row_detail, self.font_small, left_width)
                row_start = y
                for line in title_lines:
                    self.draw.text((x, y), line, font=self.font_body_bold, fill=COLOR_TEXT)
                    y += _line_height(self.font_body_bold, 4)
                for line in detail_lines:
                    self.draw.text((x, y), line, font=self.font_small, fill=COLOR_MUTED)
                    y += _line_height(self.font_small, 6)

                amount_width, amount_height = _text_size(self.font_body_bold, row_amount)
                amount_x = box[2] - CARD_PADDING - amount_width
                amount_y = row_start + 2
                self.draw.text((amount_x, amount_y), row_amount, font=self.font_body_bold, fill=COLOR_ACCENT)
                y += 12

            self.cursor_y = box[3] + CARD_GAP
            continuation = True

    def _estimate_text_card_height(self, title: str, body: list[str]) -> int:
        height = CARD_PADDING + _line_height(self.font_section, 10)
        width = CONTENT_WIDTH - (CARD_PADDING * 2)
        for block in body:
            height += len(_wrap_text(block, self.font_body, width)) * _line_height(self.font_body, 8)
            height += 12
        return max(190, height + CARD_PADDING)

    def _draw_text_card(self, title: str, body: list[str], *, accent_fill=None) -> None:
        height = self._estimate_text_card_height(title, body)
        box = self._card_box(height)
        self._draw_card_background(box, fill=accent_fill or COLOR_CARD)

        x = box[0] + CARD_PADDING
        y = box[1] + CARD_PADDING
        y = self._draw_card_heading(x, y, title)
        width = box[2] - box[0] - (CARD_PADDING * 2)
        for block_index, block in enumerate(body):
            if block_index:
                self.draw.line((x, y, box[2] - CARD_PADDING, y), fill=COLOR_BORDER, width=1)
                y += 16
            for line in _wrap_text(block, self.font_body, width):
                self.draw.text((x, y), line, font=self.font_body, fill=COLOR_TEXT)
                y += _line_height(self.font_body, 8)
            y += 10

    def _draw_summary_card(self) -> None:
        blocks = [
            f"Food subtotal: {self.order['subtotal_display']}",
            f"Pickup service fee: {self.order['service_fee_display']}",
            f"Total paid: {self.order['total_display']}",
        ]
        if self.order.get("current_eta_time"):
            if self.order.get("is_eta_delayed"):
                blocks.append(
                    f"Live ETA update: {self.order['current_eta_time']} ({self.order['eta_delay_minutes']} minutes later than first quoted)."
                )
            else:
                blocks.append(f"Current ETA remains on track for {self.order['current_eta_time']}.")
        self._draw_text_card("Totals and fulfillment summary", blocks, accent_fill=COLOR_LIGHT_ACCENT)

    def _draw_notes_card(self) -> None:
        note = self.order.get("special_instructions") or "No kitchen or pickup instructions were attached to this order."
        kitchen_note = self.order.get("kitchen_notes") or "Kitchen notes have not changed since the order was confirmed."
        self._draw_text_card("Kitchen notes", [note, kitchen_note])

    def _draw_notifications_card(self) -> None:
        blocks = []
        if self.order.get("notifications"):
            for note in self.order["notifications"]:
                blocks.append(
                    f"{note['created_at']} · {note['channel_label']} · {note['event_label']} · {note['message']}"
                )
        else:
            blocks.append("No website, email, or SMS notification has been recorded for this order yet.")
        self._draw_text_card("Notification timeline", blocks)

    def _draw_footer_note(self) -> None:
        text = (
            f"Thank you for ordering with MCQ. Present {self.order['order_number']} and "
            f"{self.order['confirmation_code']} at pickup."
        )
        width = CONTENT_WIDTH
        lines = _wrap_text(text, self.font_small, width)
        height = (len(lines) * _line_height(self.font_small, 6)) + 18
        self._ensure_space(height)
        x = PAGE_MARGIN_X
        y = self.cursor_y
        self.draw.line((x, y, PAGE_WIDTH - PAGE_MARGIN_X, y), fill=COLOR_BORDER, width=2)
        y += 16
        for line in lines:
            self.draw.text((x, y), line, font=self.font_small, fill=COLOR_MUTED)
            y += _line_height(self.font_small, 6)


def build_receipt_pdf(order: dict) -> bytes:
    return ReceiptPdfRenderer(order).build()
