import unittest
from unittest.mock import patch

from backend.main import TopicsRequest, topics


class TopicsTests(unittest.TestCase):
    @patch('backend.main.ollama_generate', return_value='Hardware demonstration')
    def test_time_only_messages_keep_boundaries_and_content(self, generate):
        chat = (
            '[09:27 AM] Karthik: Hardware sensor demonstration\nInclude fall detection\n'
            '[09:28 AM] Priya: Hardware sensor testing\n'
            '[09:29 AM] Meera: Thanks\n'
            '[09:30 AM] Arjun: Basketball tournament registration'
        )
        result = topics(TopicsRequest(chat_text=chat))['topics']
        self.assertEqual(len(result), 2)
        samples = [sample for topic in result for sample in topic['sample_messages']]
        self.assertEqual(len(samples), 3)
        self.assertTrue(any('Include fall detection' in sample for sample in samples))
        keywords = ' '.join(word for topic in result for word in topic['keywords'])
        for name in ['karthik', 'priya', 'arjun', 'meera']:
            self.assertNotIn(name, keywords)
        generate.assert_called_once()

    @patch('backend.main.ollama_generate', return_value='')
    def test_repeated_and_plain_messages_have_topics(self, generate):
        for chat in [
            '[09:27 AM] Karthik: Hardware sensor testing\n[09:28 AM] Priya: Hardware sensor testing',
            'Hardware sensor testing\nHardware sensor demonstration',
            '[09:27 AM] Karthik: Fall detection',
        ]:
            with self.subTest(chat=chat):
                result = topics(TopicsRequest(chat_text=chat))['topics']
                self.assertTrue(result)
                self.assertTrue(result[0]['topic_summary'])

    def test_empty_filler_and_last_message(self):
        for chat in ['', '[09:27 AM] Karthik: Thanks']:
            self.assertEqual(topics(TopicsRequest(chat_text=chat))['topics'], [])
        result = topics(TopicsRequest(
            chat_text='[09:27 AM] Karthik: Hardware sensor testing\n[09:28 AM] Priya: Basketball tournament registration',
            last_n=1,
        ))['topics']
        self.assertEqual(len(result), 1)
        self.assertIn('Basketball', result[0]['sample_messages'][0])


if __name__ == '__main__':
    unittest.main()
