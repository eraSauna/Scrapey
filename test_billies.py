import datetime
import unittest

from billies import displayed_date, service_section
from scrape import parse_slots_from_text


SAMPLE = """
Sauna
any
Big Billies - morning mini steam - Zandvoort
Big Billies - Zandvoort
The Barrel - Zandvoort
Pick date Following days
Big Billies - morning mini steam - Zandvoort
Fri, 18 September 2026
07:00
Available: 4
Big Billies - Zandvoort
Fri, 18 September 2026
Shared sauna
09:00
2 Available
10:30
Available: 2
12:00
Available: 6
19:30
Available: 3
21:00
FULL
The Barrel - Zandvoort
Fri, 18 September 2026
09:00
Available: 4
"""


class BilliesParserTest(unittest.TestCase):
    def test_only_target_service_is_parsed(self):
        section = service_section(SAMPLE)
        self.assertNotIn("morning mini", section)
        self.assertNotIn("The Barrel", section)
        self.assertEqual(
            parse_slots_from_text(section),
            [
                {"time": "09:00", "available": 2},
                {"time": "10:30", "available": 2},
                {"time": "12:00", "available": 6},
                {"time": "19:30", "available": 3},
                {"time": "21:00", "available": 0},
            ],
        )

    def test_date_with_comma(self):
        self.assertEqual(displayed_date(service_section(SAMPLE)), datetime.date(2026, 9, 18))


if __name__ == "__main__":
    unittest.main()
