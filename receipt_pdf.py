from __future__ import annotations

from typing import Iterable


PAGE_WIDTH = 612
PAGE_HEIGHT = 792
LEFT_MARGIN = 48
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

    content.extend(
        _text_block(
            x=LEFT_MARGIN,
            y=y,
            font="F2",
            size=22,
            lines=["MCQ Vietnamese Street Food"],
        )
    )
    y -= 28
    content.extend(
        _text_block(
            x=LEFT_MARGIN,
            y=y,
            font="F1",
            size=11,
            lines=["Scheduled pickup order receipt"],
        )
    )
    y -= 28

    overview_lines = [
        f"Order number: {order['order_number']}",
        f"Confirmation code: {order['confirmation_code']}",
        f"Placed: {order['created_at']}",
        f"Pickup time: {order['pickup_at']}",
        f"Status: {order['order_status']}",
        f"Payment: {order['payment_status']} via {order['payment_method']}",
    ]
    content.extend(_text_block(x=LEFT_MARGIN, y=y, font="F1", size=11, lines=overview_lines, leading=16))
    y -= 112

    content.extend(_text_block(x=LEFT_MARGIN, y=y, font="F2", size=13, lines=["Customer details"]))
    y -= 18
    content.extend(
        _text_block(
            x=LEFT_MARGIN,
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
    y -= 70

    content.extend(_text_block(x=LEFT_MARGIN, y=y, font="F2", size=13, lines=["Order summary"]))
    y -= 18

    item_lines: list[str] = []
    for line in order["lines"]:
        item_lines.append(
            f"{line['quantity']} x {line['name']} ({line['category']}) - {line['line_total_display']}"
        )
    content.extend(_text_block(x=LEFT_MARGIN, y=y, font="F1", size=11, lines=item_lines, leading=16))
    y -= max(40, 16 * len(item_lines) + 10)

    totals = [
        f"Subtotal: {order['subtotal_display']}",
        f"Pickup service fee: {order['service_fee_display']}",
        f"Total paid: {order['total_display']}",
    ]
    content.extend(_text_block(x=LEFT_MARGIN, y=y, font="F2", size=13, lines=["Totals"]))
    y -= 18
    content.extend(_text_block(x=LEFT_MARGIN, y=y, font="F1", size=11, lines=totals, leading=16))
    y -= 70

    note = (
        order.get("special_instructions")
        or "No additional kitchen notes were submitted for this order."
    )
    wrapped_note: list[str] = []
    for segment in _wrap_lines(f"Kitchen notes: {note}", width=78):
        wrapped_note.append(segment)
    content.extend(_text_block(x=LEFT_MARGIN, y=y, font="F2", size=13, lines=["Notes"]))
    y -= 18
    content.extend(_text_block(x=LEFT_MARGIN, y=y, font="F1", size=11, lines=wrapped_note, leading=16))
    y -= max(36, 16 * len(wrapped_note))

    footer_lines = [
        "Thank you for ordering with MCQ.",
        "Please arrive a few minutes before the scheduled pickup time and have your order number ready.",
    ]
    content.extend(_text_block(x=LEFT_MARGIN, y=y, font="F1", size=10, lines=footer_lines, leading=15))

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
