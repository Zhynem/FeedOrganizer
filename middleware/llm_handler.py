import json
import nltk
import string
from ollama import AsyncClient as ollama_async
import random
from nltk.corpus import stopwords
from nltk.probability import FreqDist
from nltk.tokenize import word_tokenize
from nltk.util import ngrams

from middleware.sqlite_handler import DBHandler

# Ensure nltk resources are downloaded
nltk.data.path.append("./nltk_data")
nltk.download("punkt_tab", download_dir="./nltk_data/", quiet=True)
nltk.download("stopwords", download_dir="./nltk_data/", quiet=True)


class LLMHandler:
    def __init__(self):
        self.db_handler = DBHandler()

    def word_frequency(self, input_str, max_words=10, gram_len=3):
        # Tokenize the transcript into words
        if input_str is None:
            return []

        words = word_tokenize(
            input_str.lower(), preserve_line=True
        )  # lowercase for normalization

        settings = self.db_handler.get_settings()
        custom_stop_words = json.loads(settings["llm_custom_stop_words"])

        # Merge custom stop words with nltk stop words
        base_sw = stopwords.words("english")
        # Add my custom words
        base_sw.extend(custom_stop_words)
        # Add all the single letters
        base_sw.extend(list(string.ascii_lowercase))
        stop_words = set(base_sw)

        # Remove stop words
        filtered_words = [
            word for word in words if word.isalnum() and word not in stop_words
        ]

        grams = ngrams(filtered_words, gram_len)

        # Get frequency distribution
        word_freq = FreqDist(filtered_words)
        gram_freq = FreqDist(grams)

        # Display the most common words
        top_words = word_freq.most_common(max_words)
        top_grams = gram_freq.most_common(max_words)

        # Filter out results that only appear a single time
        # Drop out some of the result, more so on words than grams
        top_words = [word for word, freq in top_words if freq >= 1]
        top_grams = [" ".join(gram) for gram, freq in top_grams if freq >= 1]

        return top_words, top_grams

    # noinspection PyTypeChecker
    async def categorize_video(self, title, transcript, available_categories):
        if transcript is None:
            transcript = ""

        settings = self.db_handler.get_settings()

        response_string = ""
        response_list = {}
        print()
        print(title)

        # Get most frequent non-stop words from the transcript to use
        freq_dist_size = 25 if len(transcript) <= 10000 else 25
        gram_len = 3 if len(transcript) <= 10000 else 4

        top_words, top_grams = self.word_frequency(transcript, freq_dist_size, gram_len)
        print(
            f"{len(transcript)} transcript chars | {len(top_words)} top words | {len(top_grams)} bigrams"
        )

        print("Classification beginning")
        print(top_words)
        print(top_grams)

        response = None

        example_list = [random.choice(["Educational", "Entertainment"])]
        while len(example_list) < 3:
            item = random.choice(available_categories)
            if item not in example_list:
                example_list.append(item)
            else:
                continue

        random.shuffle(available_categories)

        system_msg = settings["ollama_system_prompt"] % (
            json.dumps(example_list),
            json.dumps(available_categories),
        )

        random.shuffle(available_categories)
        if len(transcript) > 0:
            classify_msg = settings["ollama_user_prompt"] % (
                ", ".join(top_words),
                ", ".join(top_grams),
                title,
                json.dumps(available_categories),
            )
        else:
            print("No transcripts available :(")
            classify_msg = settings["ollama_user_prompt"] % (
                "No Top Words Available",
                "No Top Grams Available",
                title,
                json.dumps(available_categories),
            )

        for retry_count in range(5):
            response = await ollama_async().chat(
                model=settings["ollama_model"],
                options={
                    "num_predict": 500,
                    "num_ctx": int(settings["ollama_ctx_size"]),
                    "cache_prompt": False,
                },
                messages=[
                    {
                        "role": "system",
                        "content": system_msg,
                    },
                    {
                        "role": "user",
                        "content": classify_msg,
                    },
                ],
            )
            try:
                r = response["message"]["content"].replace("]]", "]")
                r = r.replace("```python", "")
                r = r.replace("```", "")
                data = list(json.loads(r))
                assert isinstance(data, list)
                break
            except Exception as e:
                print(response)
                print(e)
                continue

        try:
            print("Proper response obtained!")
            r = response["message"]["content"].replace("]]", "]")
            r = r.replace("```python", "")
            r = r.replace("```", "")
            response_string = r
            response_list = list(json.loads(r))
            response_tokens = response["eval_count"]
            inp_tokens = response["prompt_eval_count"]
            processing_time = response["total_duration"] / 1e9
            print(
                f"Proc Time: {processing_time:0.2f} | Transcript Len: {len(transcript)} | Inp Tokens: {inp_tokens} | Out Tokens: {response_tokens} "
            )

        except Exception as e:
            print("=============== EXCEPTION ===============")
            print(e)
            print(response_list)
            print(response_string)
            print("=============== EXCEPTION ===============")
            print()

        made_up = 0
        for item in response_list:
            if item not in available_categories:
                response_list.remove(item)
                made_up += 1

        if ("Educational" not in response_list) and (
            "Entertainment" not in response_list
        ):
            response_list.append("Entertainment")

        print(f"Assigned: {response_list} | Removed {made_up} made up categories.")

        return sorted(response_list)
