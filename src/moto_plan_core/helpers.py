import re


class HtmlHelper:
    @staticmethod
    def strip_tags(html: str) -> str:
        text = re.sub(r"<[^>]+>", " ", html)
        text = HtmlHelper._decode_numeric_entities(text)
        for entity, ch in [("&nbsp;", " "), ("&amp;", "&")]:
            text = text.replace(entity, ch)
        return " ".join(text.split())

    @staticmethod
    def _decode_numeric_entities(text: str) -> str:
        result = text
        for m in re.finditer(r"&#(\d+);", result):
            try:
                result = result[:m.start()] + chr(int(m.group(1))) + result[m.end():]
            except ValueError:
                pass
        return result

    @staticmethod
    def decode_entities(text: str) -> str:
        return HtmlHelper._decode_numeric_entities(text)
