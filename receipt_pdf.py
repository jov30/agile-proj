from __future__ import annotations

from typing import Iterable


PAGE_WIDTH = 612
PAGE_HEIGHT = 792
LEFT_MARGIN = 48
RIGHT_MARGIN = 564
TOP_Y = 756


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _wrap_lines(text: str, width: int = 76) -> list[str]:
    words = text.split()
    if not words:
        return [""]

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= width:
            current = candidate
            continue
        lines.append(current)
        current = word
    lines.append(current)
    return lines


def _text_block(
    *,
    x: int,
    y: int,
    font: str,
    size: int,
    lines: Iterable[str],
    leading: int | None = None,
) -> list[str]:
    rendered = list(lines)
    if not rendered:
        rendered = [""]
    commands = [
        "BT",
        f"/{font} {size} Tf",
        f"{x} {y} Td",
        f"{leading or int(size * 1.45)} TL",
    ]
    for index, line in enumerate(rendered):
        if index:
            commands.append("T*")
        commands.append(f"({_escape(line)}) Tj")
    commands.append("ET")
    return commands


def _filled_rect(x: int, y: int, width: int, height: int, rgb: tuple[float, float, float]) -> list[str]:
    r, g, b = rgb
    return [
        "q",
        f"{r:.3f} {g:.3f} {b:.3f} rg",
        f"{x} {y} {width} {height} re f",
        "Q",
    ]


def _stroked_rect(x: int, y: int, width: int, height: int, rgb: tuple[float, float, float]) -> list[str]:
    r, g, b = rgb
    return [
        "q",
        f"{r:.3f} {g:.3f} {b:.3f} RG",
        "1 w",
        f"{x} {y} {width} {height} re S",
        "Q",
    ]


def _build_pdf(objects: list[bytes]) -> bytes:
    parts = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]

    for index, obj in enumerate(objects, start=1):
        offsets.append(sum(len(part) for part in parts))
        parts.append(f"{index} 0 obj\n".encode("ascii"))
        parts.append(obj)
        parts.append(b"\nendobj\n")

    startxref = sum(len(part) for part in parts)
    parts.append(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    parts.append(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        parts.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    parts.append(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{startxref}\n%%EOF"
        ).encode("ascii")
    )
    return b"".join(parts)


def build_receipt_pdf(order: dict) -> bytes:
    content: list[str] = []
    y = TOP_Y
    is_instant = bool(order.get("is_instant"))
    mode_subtitle = "Instant queue invoice receipt" if is_instant else "Scheduled pickup invoice receipt"

    content.extend(_filled_rect(LEFT_MARGIN, 722, 516, 42, (0.957, 0.420, 0.110)))
    content.extend(
        _text_block(
            x=LEFT_MARGIN + 16,
            y=744,
            font="F2",
            size=22,
            lines=["MCQ Vietnamese Street Food"],
        )
    )
    content.extend(
        _text_block(
            x=LEFT_MARGIN + 16,
            y=728,
            font="F1",
            size=11,
            lines=[mode_subtitle],
        )
    )
    y = 698

    fulfillment_line = (
        f"Queue: {order.get('queue_display')} at {order.get('counter_label')}"
        if is_instant
        else f"Pickup time: {order['pickup_at']}"
    )
    overview_lines = [
        f"Order number: {order['order_number']}",
        f"Confirmation code: {order['confirmation_code']}",
        f"Placed: {order['created_at']}",
        fulfillment_line,
        f"Fulfillment: {order.get('fulfillment_label', 'Scheduled pickup')}",
        f"Status: {order['order_status']}",
        f"Payment: {order['payment_status']} via {order['payment_method']}",
    ]
    if is_instant and order.get("quoted_wait_display"):
        overview_lines.append(f"Quoted wait: {order['quoted_wait_display']}")
    content.extend(_stroked_rect(LEFT_MARGIN, 600, 516, 88, (0.812, 0.682, 0.510)))
    content.extend(_text_block(x=LEFT_MARGIN + 14, y=y, font="F2", size=13, lines=["Order overview"]))
    y -= 18
    content.extend(_text_block(x=LEFT_MARGIN + 14, y=y, font="F1", size=11, lines=overview_lines, leading=15))

    y = 572
    content.extend(_stroked_rect(LEFT_MARGIN, 500, 250, 62, (0.812, 0.682, 0.510)))
    content.extend(_text_block(x=LEFT_MARGIN + 14, y=y, font="F2", size=13, lines=["Customer details"]))
    y -= 18
    content.extend(
        _text_block(
            x=LEFT_MARGIN + 14,
            y=y,
            font="F1",
            size=11,
            lines=[
                order["customer_name"],
                order["customer_email"],
                order["customer_phone"],
            ],
            leading=16,
        )
    )

    y = 572
    content.extend(_stroked_rect(314, 500, 250, 62, (0.812, 0.682, 0.510)))
    payment_lines = [
        f"Reference: {order['payment_reference']}",
        f"Status: {order['payment_status']}",
        f"Method: {order['payment_method']}",
    ]
    if order.get("card_last4"):
        payment_lines.append(f"Card ending: {order['card_last4']}")
    if order.get("latest_payment_attempt"):
        payment_lines.append(f"Attempt log: {order['latest_payment_attempt']['reference']}")
    content.extend(_text_block(x=328, y=y, font="F2", size=13, lines=["Payment log"]))
    y -= 18
    content.extend(_text_block(x=328, y=y, font="F1", size=11, lines=payment_lines, leading=15))

    y = 474
    content.extend(_stroked_rect(LEFT_MARGIN, 290, 516, 172, (0.812, 0.682, 0.510)))
    content.extend(_text_block(x=LEFT_MARGIN + 14, y=y, font="F2", size=13, lines=["Order summary"]))
    y -= 18

    item_lines: list[str] = []
    for line in order["lines"]:
        item_lines.append(
            f"{line['quantity']} x {line['name']} ({line['category']}) - {line['line_total_display']}"
        )
    content.extend(_text_block(x=LEFT_MARGIN + 14, y=y, font="F1", size=11, lines=item_lines, leading=16))

    y = 262

    totals = [
        f"Subtotal: {order['subtotal_display']}",
        f"Service fee: {order['service_fee_display']}",
        f"Total paid: {order['total_display']}",
    ]
    content.extend(_stroked_rect(LEFT_MARGIN, 196, 516, 56, (0.812, 0.682, 0.510)))
    content.extend(_text_block(x=LEFT_MARGIN + 14, y=y, font="F2", size=13, lines=["Totals"]))
    y -= 18
    content.extend(_text_block(x=LEFT_MARGIN + 14, y=y, font="F1", size=11, lines=totals, leading=15))

    y = 168

    note = (
        order.get("special_instructions")
        or "No additional kitchen notes were submitted for this order."
    )
    wrapped_note: list[str] = []
    for segment in _wrap_lines(f"Kitchen notes: {note}", width=78):
        wrapped_note.append(segment)
    content.extend(_stroked_rect(LEFT_MARGIN, 86, 516, 72, (0.812, 0.682, 0.510)))
    content.extend(_text_block(x=LEFT_MARGIN + 14, y=y, font="F2", size=13, lines=["Notes"]))
    y -= 18
    content.extend(_text_block(x=LEFT_MARGIN + 14, y=y, font="F1", size=11, lines=wrapped_note, leading=15))
    y = 52

    footer_lines = [
        "Thank you for ordering with MCQ.",
        (
            f"Collect from {order.get('counter_label')} with queue {order.get('queue_display')} and order number ready."
            if is_instant
            else "Please arrive a few minutes before the scheduled pickup time and have your order number ready."
        ),
    ]
    content.extend(_text_block(x=LEFT_MARGIN, y=y, font="F1", size=10, lines=footer_lines, leading=14))

    stream = "\n".join(content).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>"
        ).encode("ascii"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    return _build_pdf(objects)
