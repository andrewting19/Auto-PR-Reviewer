#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
import os
import backoff
import openai
import tiktoken
from prompts import system_prompt

openai.api_key = os.getenv("OPENAI_API_KEY")
if os.getenv("OPENAI_API_BASE"):
    openai.api_base = os.getenv("OPENAI_API_BASE")
    if "azure" in os.getenv("OPENAI_API_BASE"):
        openai.api_type = "azure"
        openai.api_version = "2023-03-15-preview"


class OpenAIClient:
    '''OpenAI API client'''

    def __init__(self, model, temperature, frequency_penalty, presence_penalty,
                 max_tokens=4000, min_tokens=256):
        self.model = model
        self.temperature = temperature
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
        self.encoder = tiktoken.get_encoding("gpt2")
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.openai_kwargs = {'model': self.model}
        if openai.api_type == "azure":
            self.openai_kwargs = {'engine': self.model}

    @backoff.on_exception(backoff.expo,
                          (openai.error.RateLimitError,
                           openai.error.APIConnectionError,
                           openai.error.ServiceUnavailableError),
                          max_time=300)
    def get_completion(self, prompt) -> str:
        if self.model.startswith("gpt-"):
            return self.get_completion_chat(prompt)
        else:
            return self.get_completion_text(prompt)

    def get_completion_chat(self, prompt) -> str:
        '''Invoke OpenAI API to get chat completion'''
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]
        functions = [
            {
                "name": "raise_issues",
                "description": "Adds a review comment for a specific line of code in Github pull request",
                "parameters": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {
                                "type": "int",
                                "description": "The severity of the issue, measured as an integer points. 1 point for nits, 3 points for optimizations, and 5 points for errors."
                            },
                            "line": {
                                "type": "int",
                                "description": "The line of the blob in the pull request diff that the comment applies to. Set line = -1 to comment on the whole file."
                            },
                            "body": {
                                "type": "string",
                                "description": "The text of the review comment"
                            }
                        },
                        "required": ["severity", "line", "body"]
                    }
                }
            }
        ]
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
        return response.choices[0].message

    def get_completion_text(self, prompt) -> str:
        '''Invoke OpenAI API to get text completion'''
        prompt_message = f'{system_prompt}\n{prompt}'
        response = openai.Completion.create(
            prompt=prompt_message,
            temperature=self.temperature,
            best_of=1,
            frequency_penalty=self.frequency_penalty,
            presence_penalty=self.presence_penalty,
            request_timeout=100,
            max_tokens=self.max_tokens - len(self.encoder.encode(prompt_message)),
            stream=False, **self.openai_kwargs)
        return response.choices[0].message

    def get_pr_prompt(self, title, body, changes) -> str:
        '''Generate a prompt for a PR review'''
        return f"""
        ### Pull Request Title: {title}

        ### Pull Request Body: 
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

        ### Pull Request Body: 
        {body}

        ### Changes for file {filename}:
        ```
        {changes}
        ```
        """
