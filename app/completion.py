#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
import os
import backoff
import openai
import tiktoken
from prompts import system_prompt

openai.api_key = os.getenv("OPENAI_API_KEY")


class OpenAIClient:
    '''OpenAI API client'''

    def __init__(self, model, temperature, frequency_penalty, presence_penalty,
                 max_tokens=8000, min_tokens=256):
        self.model = model
        self.temperature = temperature
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
        self.encoder = tiktoken.get_encoding("gpt2")
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.openai_kwargs = {'model': self.model}

    @backoff.on_exception(backoff.expo,
                          (openai.error.RateLimitError,
                           openai.error.APIConnectionError,
                           openai.error.ServiceUnavailableError),
                          max_time=300)
    def get_image(self, prompt, size=1024, n=1):
        return openai.Image.create(prompt=prompt, n=n, size=f"{size}x{size}")['data'][0]['url']

    @backoff.on_exception(backoff.expo,
                          (openai.error.RateLimitError,
                           openai.error.APIConnectionError,
                           openai.error.ServiceUnavailableError),
                          max_time=300)
    def get_completion(self, prompt, sys_prompt=system_prompt, with_function=True) -> str:
        '''Invoke OpenAI API to get chat completion'''
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ]
        functions = [
            {
                "name": "raise_issues",
                "description": "Adds a review comment for a specific line of code in Github pull request",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "severity": {
                                        "type": "integer",
                                        "description": "The severity of the issue, measured as an integer points. 1 point for nits, 3 points for optimizations, and 5 points for errors."
                                    },
                                    "line": {
                                        "type": "integer",
                                        "description": "The line of the blob in the pull request diff that the comment applies to. Set line = -1 to comment on the whole file."
                                    },
                                    "body": {
                                        "type": "string",
                                        "description": "The text of the review comment containing feedback"
                                    }
                                },
                                "required": ["severity", "line", "body"]
                            }
                        }
                    },
                    "required": ["data"],
                }
            }
        ]
        if with_function:
            response = openai.ChatCompletion.create(
                messages=messages,
                functions=functions,
                function_call={"name": "raise_issues"},
                temperature=self.temperature,
                frequency_penalty=self.frequency_penalty,
                presence_penalty=self.presence_penalty,
                request_timeout=100,
                max_tokens=self.max_tokens - len(self.encoder.encode(f'{system_prompt}\n{prompt}')),
                stream=False, **self.openai_kwargs)
        else:
            response = openai.ChatCompletion.create(
                messages=messages,
                temperature=self.temperature,
                frequency_penalty=self.frequency_penalty,
                presence_penalty=self.presence_penalty,
                request_timeout=100,
                max_tokens=self.max_tokens - len(self.encoder.encode(f'{system_prompt}\n{prompt}')),
                stream=False, **self.openai_kwargs)
        return response.choices[0].message

    def get_pr_prompt(self, title, body, changes) -> str:
        '''Generate a prompt for a PR review'''
        return f"""
        ### Pull Request Title: {title}

        ### Pull Request Description: 
        {body}

        ### Pull Request Changes:
        ```
        {changes}
        ```
        """

    def get_file_prompt(self, title, body, filename, changes) -> str:
        '''Generate a prompt for a file review'''
        return f"""        
        ### Pull Request Title: {title}

        ### Pull Request Description: 
        {body}

        ### Changes for file {filename}. Removed lines begin with minus (-). Added lines begin with plus (+):
        ```
        {changes}
        ```
        """

    def get_file_prompt_contents(self, title, body, filename, contents) -> str:
        return f"""        
        ### Please respond with your feedback for this file. Each point of feedback should include severity, line, and comment.

        ### Contents for file {filename}:
        ```
        {contents}
        ```
        """


if __name__ == "__main__":
    import githubs
    openai_client = OpenAIClient(
        model="gpt-4",
        temperature=0.2,
        frequency_penalty=0,
        presence_penalty=0)
    github_client = githubs.GithubClient(
        openai_client=openai_client,
        review_per_file=True,
        comment_per_file=False,
        blocking=False)
    prompt, img = github_client.generate_meme_image_url()
    print(img)
    prompt = '''
    ### Pull Request Title: test

        ### Pull Request Description: 
        Testing this 

        ### Contents for file services/Announcers.py:
        ```
        b'import time\nimport numpy as np\nimport pandas as pd\nfrom controllers.discord import *\n\n\nclass Announcer:\n\n    def print_ou_lines(self, df, start_count=1, quiet=False):\n        count = start_count\n        printed_str = ""\n        for i in range(len(df)):\n            row = df.iloc[i]\n            league = f"{row[\'league\'][0:3]:<3}" if row["league"] is not None else "   "\n            role = f" ({row[\'role\']})"\n            m = f"Map {row[\'map\']:<3}"\n            next_line = f"{count:>3} | Prob {max(row[\'bet_prob\'], 1 - row[\'bet_prob\'])*100:.1f}% | {league} | {row[\'name\'][0:13] + role:^18} {\'OVER \' if row[\'bet_prob\'] > 0.5 else \'UNDER\'}  {row[\'line\']:<4} kills | {m} | {row[\'team\'].title() if not pd.isna(row[\'team\']) else row[\'team\']} vs {row[\'vs_team\'].title() if not pd.isna(row[\'vs_team\']) else row[\'vs_team\']} | {row[\'source\']}"\n            printed_str += next_line + "\\n"\n            if not quiet:\n                print(next_line)\n            count += 1\n        return printed_str, count\n\n    def announce_kill_lines(self, df, source="", alttext=None):\n        count = 1\n        text = alttext if alttext is not None else f"\xf0\x9f\xa4\x96\xf0\x9f\xa7\xa0\xf0\x9f\x92\xaf Get your AI generated {source} bets right here"\n        announce_lines_on_discord(\n            text, everyone=False, gamba_num=3 if source == "PrizePicks" else 2)\n        df["max_bet_prob_or_complement"] = np.maximum(\n            df["bet_prob"], 1 - df["bet_prob"])\n        df = df.sort_values(by="max_bet_prob_or_complement", ascending=False)\n        for i in range(0, len(df), 10):\n            printed_str, count = self.print_ou_lines(\n                df.iloc[i:i + 10], count, quiet=True)\n            announce_lines_on_discord(\n                printed_str, everyone=False, code_text=True, gamba_num=3 if source == "PrizePicks" else 2)\n            time.sleep(0.5)\n\n    def announce_changes(self, new_lines=None, deleted_lines=None):\n        """\n        Announces any new or deleted PrizePicks or Underdog lines in their respective channels. \n        """\n        for lines, deleted in zip([deleted_lines, new_lines], [True, False]):\n            if lines is None or len(lines) == 0:\n                continue\n            for source in ["PrizePicks", "Underdog"]:\n                temp = lines[lines["source"] == source]\n                if len(temp) > 0:\n                    self.announce_new_or_deleted(temp, source, deleted)\n\n    def announce_new_or_deleted(self, df, source="", deleted=False):\n        count = 1\n        if not deleted:\n            announce_lines_on_discord(\n                f"New {source} lines just dropped \xf0\x9f\x91\x87\xf0\x9f\x91\x87\xf0\x9f\x91\x87", everyone=False, gamba_num=3 if source == "PrizePicks" else 2)\n        else:\n            announce_lines_on_discord(\n                f"Old {source} lines deleted \xf0\x9f\x99\x85\xe2\x9d\x8c\xf0\x9f\x93\x89", everyone=False, gamba_num=3 if source == "PrizePicks" else 2)\n        df["max_bet_prob_or_complement"] = np.maximum(\n            df["bet_prob"], 1 - df["bet_prob"])\n        df = df.sort_values(by="max_bet_prob_or_complement", ascending=False)\n        for i in range(0, len(df), 10):\n            printed_str, count = self.print_ou_lines(\n                df.iloc[i:i + 10], count, quiet=True)\n            announce_lines_on_discord(\n                printed_str, everyone=False, code_text=True, gamba_num=3 if source == "PrizePicks" else 2)\n            time.sleep(0.5)\n\n    def debug(self, msg, everyone=False):\n        send_discord_debug(msg, everyone)\n'
        ```'''
    print(openai_client.encoder.encode(prompt))
    completion = openai_client.get_completion(prompt, with_function=False)
    content = completion["content"]
    print(completion)
    print(content)