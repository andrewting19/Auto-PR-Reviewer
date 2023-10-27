#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
import json
import os
import requests
import random
from github import Github


# List of event types
EVENT_TYPE_PUSH = "push"
EVENT_TYPE_COMMENT = "comment"
EVENT_TYPE_PULL_REQUEST = "pull_request"
EVENT_TYPE_OTHER = "other"


class GithubClient:
    '''Github API client'''

    def __init__(self, openai_client, review_per_file=False, comment_per_file=False, blocking=False):
        self.openai_client = openai_client
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.github_client = Github(self.github_token)
        self.review_tokens = self.openai_client.max_tokens - self.openai_client.min_tokens
        self.review_per_file = review_per_file
        self.comment_per_file = comment_per_file
        self.blocking = blocking

    def get_event_type(self, payload) -> str:
        '''Determine the type of event'''
        if payload.get("head_commit") is not None:
            return EVENT_TYPE_PUSH

        if payload.get("pull_request") is not None:
            return EVENT_TYPE_PULL_REQUEST

        if payload.get("comment") is not None:
            return EVENT_TYPE_COMMENT

        return EVENT_TYPE_OTHER

    def get_pull_request(self, payload):
        '''Get the pull request'''
        repo = self.github_client.get_repo(os.getenv("GITHUB_REPOSITORY"))
        pr = repo.get_pull(payload.get("number"))
        changes = requests.get(pr.url,
                               timeout=30,
                               headers={"Authorization": "Bearer " + self.github_token,
                                        "Accept": "application/vnd.github.v3.diff"},
                               ).text
        return pr, changes

    def cut_changes(self, previous_filename, filename, patch):
        '''Cut the changes to fit the max tokens'''
        if previous_filename is None:
            previous_filename = filename

        # add a patch header
        patch = f'diff --git a/{previous_filename} b/{filename}\n{patch}'
        if len(self.openai_client.encoder.encode(patch)) < self.review_tokens:
            return patch

        # TODO: it is not a good idea to cut the contents, need figure out a better way
        lines = patch.splitlines()
        print(
            f"The changes for {filename} is too long, contents would be cut to fit the max tokens")
        i = len(lines)
        while i > 0:
            i -= 1
            line = '\n'.join(lines[:i])
            if len(self.openai_client.encoder.encode(line)) < self.review_tokens:
                return line
        return ''

    def get_issues(self, prompt) -> list:
        '''Gets a list of issues: { severity: int, line: int, body: str } '''
        try:
            completion = self.openai_client.get_completion(prompt)
            if completion is not None and "function_call" in completion:
                return json.loads(completion["function_call"]["arguments"]).get("data", [])
            return []
        except Exception as e:
            print(f"OpenAI failed on prompt {prompt} with exception {e}")
            return []

    def get_file_comments(self, prompt):
        try:
            completion = self.openai_client.get_completion(prompt, with_function=False)
            if completion is not None and "content" in completion:
                return completion["content"]
            return None
        except Exception as e:
            print(f"OpenAI failed on prompt {prompt} with exception {e}")
            return None


    def review_by_issues(self, pr):
        # Review each file changes separately
        files_changed = pr.get_files()
        total_severity = 0
        review_comments = []
        for file in files_changed:
            file_changes = self.cut_changes(
                file.previous_filename, file.filename, file.patch)
            prompt = self.openai_client.get_file_prompt(
                pr.title, pr.body, file.filename, file_changes)
            issues = self.get_issues(prompt)
            for issue in issues:
                print(prompt)
                print(issue)
                severity = issue.get("severity", 0)
                line = issue.get("line", -1)
                body = issue.get("body", "")

                # Create a review comment on the file
                self.submit_pr_comment(pr, file.filename, severity, line, body)
                review_comments.append({
                    "path": file.filename,
                    "body": body,
                    "line": line,
                })
                total_severity += severity

        review_status = "APPROVED" if total_severity < 5 else "REQUEST_CHANGES"
        review_body = f"Status: {review_status}\nTotal Severity: {total_severity}\nTotal Comments: {len(review_comments)}"
        pr.create_review(list(pr.get_commits())[-1], body=review_body,
                         event=review_status)  # , comments=review_comments)

    def generate_meme_image_url(self):
        seed = "❤️🎃✅🔥💀🫶✨😊😂⭐👻👍✔️🎉👉👀👇🌔😭🚀🥹➡️👋😉🙏🫡😍🤔💪🤓"
        seed = seed[random.randint(0, len(seed) - 1)]
        system_prompt = "You are a creative meme generator. Your task is to take a random emoji as a seed and generate a prompt that an image generation model will use to create a meme. The meme should be funny and relatable to engineers and employees of the crypto startup Uniswap Labs. Use the emoji to inspire the theme or subject of the meme. Let's make some memes!"
        try:
            prompt = f"Respond with 10 descriptive words based on this emoji that could be used to generate a funny meme: {seed}. Respond with the 10 words and nothing else, don't enumerate them either."
            meme_prompt = self.openai_client.get_completion(prompt,
                                                            system_prompt, with_function=False)
            print(seed, prompt)
            if meme_prompt is None or "content" not in meme_prompt:
                return None
            meme_prompt = meme_prompt["content"]
            return meme_prompt, self.openai_client.get_image(f"cartoon internet meme celebration {meme_prompt}")
        except Exception as e:
            print(f"OpenAI failed on meme prompt generation with exception {e}")
            return None

    def add_review_meme(self, pr):
        res = self.generate_meme_image_url()
        if res is None:
            return
        print(res)
        prompt, image_url = res
        pr.create_review(list(pr.get_commits())[-1], body=f"Great work! Here's a congratulatory AI generated meme!\n\n ![meme]({image_url})",
                         event="COMMENT")

    def review_by_files(self, pr):
        repo = self.github_client.get_repo(os.getenv("GITHUB_REPOSITORY"))
        latest_commit = list(pr.get_commits())[-1]
        for file in latest_commit.files:
            try:
                filename = file.filename
                file_contents = repo.get_contents(filename, ref=latest_commit.sha).decoded_content
                prompt = self.openai_client.get_file_prompt_contents(pr.title, pr.body, filename, file_contents)
                comments = self.get_file_comments(prompt)
                print("-----")
                print(prompt)
                print("-----")
                print(comments)
                if comments is not None:
                    pr.create_review_comment(body=comments, commit=latest_commit, path=filename, subject_type="file")
            except Exception as e:
                print(f"Failed {filename} with error: {e}")
        self.add_review_meme(pr)

    def review_pr(self, payload):
        '''Review a PR'''
        pr, changes = self.get_pull_request(payload)
        self.review_by_files(pr)

    def submit_pr_comment(self, pr, filename, severity, line, body):
        content = f"""Severity: {severity}\nLine: {line}\n\n{body}"""
        # if line < 0:
        return pr.create_review_comment(body=content,
                                 commit=list(pr.get_commits())[-1],
                                 path=filename,
                                 subject_type="file")
        # else:
        #     return pr.create_review_comment(body=content,
        #                              commit=list(pr.get_commits())[-1],
        #                              path=filename,
        #                              line=line)
