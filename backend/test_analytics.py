import unittest

from backend.main import AnalyticsRequest, analytics, parse_chat_metadata


class AnalyticsTests(unittest.TestCase):
    def test_time_only_chat_and_multiline_messages(self):
        chat = (
            "[09:27 AM] Karthik: Fall detection.\nMore hardware details.\n"
            "[09:27 PM] Priya: Hardware demo tomorrow.\n"
            "[09:28 PM] Priya: Karthik will present the hardware demo."
        )
        result = analytics(AnalyticsRequest(chat_text=chat))
        self.assertEqual(result['total_messages'], 3)
        self.assertEqual(result['messages_per_user'], {'Karthik': 1, 'Priya': 2})
        self.assertEqual(result['most_active_hour'], '21:00')
        self.assertIsNone(result['most_active_day'])
        words = {item['word']: item['count'] for item in result['top_words']}
        self.assertEqual(words['hardware'], 3)
        self.assertNotIn('karthik', words)
        self.assertNotIn('the', words)
        recent = analytics(AnalyticsRequest(chat_text=chat, last_n=1))
        self.assertEqual(recent['messages_per_user'], {'Priya': 1})

    def test_export_formats(self):
        for line in [
            '12/09/2026, 9:27 PM - Priya: Hardware demo',
            '[21:27, 12/09/2026] Priya: Hardware demo',
            '\u200e[12/09/2026, 9:27:00\u202fPM] Priya: Hardware demo',
        ]:
            with self.subTest(line=line):
                self.assertEqual(parse_chat_metadata(line)['user'], 'Priya')
                result = analytics(AnalyticsRequest(chat_text=line))
                self.assertEqual(result['most_active_hour'], '21:00')
                self.assertEqual(result['most_active_day'], '12/09/2026')

    def test_midnight_noon_and_empty_chat(self):
        for time, expected in [('12:00 AM', '00:00'), ('12:00 PM', '12:00')]:
            result = analytics(AnalyticsRequest(chat_text=f'[{time}] Priya: Demo'))
            self.assertEqual(result['most_active_hour'], expected)
        self.assertEqual(analytics(AnalyticsRequest(chat_text=''))['total_messages'], 0)


if __name__ == '__main__':
    unittest.main()
