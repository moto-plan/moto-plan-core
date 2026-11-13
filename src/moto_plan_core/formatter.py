from .models import Event


class EventFormatter:
    @staticmethod
    def format_date(event: Event) -> str:
        if event.day and event.month_num:
            if event.day_end and event.day_end != event.day:
                base = f"{event.day:02d}.{event.month_num:02d}–{event.day_end:02d}.{event.month_end:02d}"
                return f"{base}.{event.year}" if event.year else base
            date_str = f"{event.day:02d}.{event.month_num:02d}"
            return f"{date_str}.{event.year}" if event.year else date_str
        return event.date.strip() if event.date else "?"

    @staticmethod
    def format_events(events: list[Event]) -> None:
        header = f"{'Agency':<18} {'Date':<22} {'Track':<24} {'Day(s)':<22} {'Price(s)':>16}  {'Sold':>6}  {'Note'}"
        print(header)
        print("-" * len(header))
        for ev in events:
            date_str = EventFormatter.format_date(ev)
            days = ", ".join(ev.day_of_week) if ev.day_of_week else ""
            price_parts: list[str] = []
            extra_prices: list[str] = []
            for p in ev.prices:
                if p["currency"] == "TBD":
                    price_parts.append("PŘIPRAVUJEME")
                    continue
                label = p["day_label"].upper() or ""
                amount = f"{p['amount']:,.0f}".replace(",", ".")
                formatted = f"{label} {amount}" if label else amount
                price_parts.append(formatted)

            if len(ev.prices) > 1:
                amounts = [p["amount"] for p in ev.prices if p["currency"] != "TBD"]
                if amounts:
                    min_amt = f"{min(amounts):,.0f}".replace(",", ".")
                    price_str = f"od {min_amt}"
                    extras = [p for p in price_parts if not p.startswith("od")]
                    extra_prices = extras
                else:
                    price_str = "  ".join(price_parts) if price_parts else ""
            elif price_parts:
                price_str = price_parts[0]
            else:
                price_str = ""

            note = ev.note
            if extra_prices:
                note = f"{note} ({', '.join(extra_prices)})" if note else f"({' '.join(extra_prices)})"

            sold_str = "x" if ev.sold_out else ""
            print(f"{ev.agency:<18} {date_str:<22} {ev.track_name:<24} {days:<22} {price_str:>16}  {sold_str:>6}  {note}")
