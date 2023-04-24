import importlib.util
import os

import requests

from .python_interpreter import evaluate


# Move to util when this branch is ready to merge
def is_openai_available():
    return importlib.util.find_spec("openai") is not None


if is_openai_available():
    import openai

# docstyle-ignore
OPEN_ASSISTANT_PROMPT_TEMPLATE = """I will ask you to perform a task, your job is to come up with a series of simple commands in Python that will perform the task.
To help you, I will give you access to a set of tools that you can use. Each tool is a Python function and has a description explaining the task it performs, the inputs it expects and the outputs it returns.
Each instruction in Python should be a simple assignement.
The final result should be stored in a variable named `result`. You can also print the result if it makes sense to do so.
You should only use the tools necessary to perform the task.

Task: "Answer the question in the variable `question` about the image stored in the variable `image`. The question is in French."

Tools:
- tool_1 is a function that translates text from French to English. It takes an input named `text` which should be the text in French and returns a dictionary with a single key `'translation_text'` that contains the translation in Enlish.
- tool_2 is a function that generates speech from a given text in English. It takes an input named `text` which should be the text in English and returns the path to a filename containing an audio of this text read.
- tool_3 is a function that answers question about images. It takes an input named `text` which should be the question in English and an input `image` which should be an image, and outputs a text that is the answer to the question.

Answer:
```py
translated_question = tool_1(text=question)['translation_text']
result = tool_3(text=translated_question, image=image)
print(f"The answer is {result}")
```

This is the format. Begin!

Task: "<<prompt>>"

Tools:
<<tools>>

Answer:
"""


# docstyle-ignore
OPENAI_PROMPT_TEMPLATE = """I will ask you to perform a task, your job is to come up with a series of simple commands in Python that will perform the task. To help you, I will give you access to a set of tools that you can use. Each tool is a Python function and has a description explaining the task it performs, the inputs it expects and the outputs it returns. Each instruction in Python should be a simple assignement.

Task: "Answer the question in the variable `question` about the image stored in the variable `image`. The question is in French."

Tools:
- tool_1 is a function that translates text from French to English. It takes an input named `text` which should be the text in French and returns a dictionary with a single key `'translation_text'` that contains the translation in Enlish.
- tool_2 is a function that generates speech from a given text in English. It takes an input named `text` which should be the text in English and returns the path to a filename containing an audio of this text read.
- tool_3 is a function that answers question about images. It takes an input named `text` which should be the question in English and an input `image` which should be an image, and outputs a text that is the answer to the question.

Answer:
```py
translated_question = tool_1(text=question)['translation_text']
answer = tool_3(text=translated_question, image=image)
```

This is the format. Begin!

Task: {prompt}

Tools:
{tools}

Answer:
"""


class Agent:
    def perform(self, task, tools, **kwargs):
        code = self.generate_code(task, tools)
        # Clean up the code received
        code_lines = code.split("\n")
        in_block_code = "```" in code_lines[0]
        additional_explanation = []
        if in_block_code:
            code_lines = code_lines[1:]
        for idx in range(len(code_lines)):
            if in_block_code and "```" in code_lines[idx]:
                additional_explanation = code_lines[idx + 1 :]
                code_lines = code_lines[:idx]
                break

        clean_code = "\n".join(code_lines)

        all_tools = {"print": print}
        all_tools.update({f"tool_{idx}": tool for idx, tool in enumerate(tools)})

        print(f"==Code generated by the agent==\n{clean_code}\n\n")
        if len(additional_explanation) > 0:
            explanation = "\n".join(additional_explanation).strip()
            print(f"==Additional explanation from the agent==\n{explanation}\n\n")
        print("==Result==")

        return evaluate(clean_code, all_tools, kwargs)


class OpenAssistantAgent(Agent):
    def __init__(self, url_endpoint, token):
        self.url_endpoint = url_endpoint
        self.token = token

    def generate_code(self, task, tools):
        headers = {"Authorization": self.token}
        tool_descs = [f"- tool_{i} is a function that {tool.description}" for i, tool in enumerate(tools)]
        prompt = OPEN_ASSISTANT_PROMPT_TEMPLATE.replace("<<prompt>>", task)
        prompt = prompt.replace("<<tools>>", "\n".join(tool_descs))
        inputs = {
            "inputs": prompt,
            "parameters": {"max_new_tokens": 200, "do_sample": True, "temperature": 0.5, "return_full_text": False},
        }
        response = requests.post(self.url_endpoint, json=inputs, headers=headers)
        if response.status_code != 200:
            raise ValueError(f"Error {response.status_code}: {response.json}")
        return response.json()[0]["generated_text"]


class OpenAIAgent(Agent):
    prompt_template = OPENAI_PROMPT_TEMPLATE

    def __init__(self, model="gpt-3.5-turbo", api_key=None):
        if not is_openai_available():
            raise ImportError("Using `OpenAIAgent` requires `openai`: `pip install openai`.")

        if api_key is None:
            api_key = os.environ.get("OPENAI_API_KEY", None)
        if api_key is None:
            raise ValueError(
                "You need an openai key to use `OpenAIAgent`. You can get one here: Get one here "
                "https://openai.com/api/`. If you have one, set it in your env with `os.environ['OPENAI_API_KEY'] = "
                "xxx."
            )
        else:
            openai.api_key = api_key
        self.model = model

    def generate_code(self, task, tools):
        tool_descs = [f"- tool_{i} is a function that {tool.description}" for i, tool in enumerate(tools)]
        prompt = OPENAI_PROMPT_TEMPLATE.replace("{prompt}", task)
        prompt = prompt.replace("{tools}", "\n".join(tool_descs))

        result = openai.ChatCompletion.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        return result["choices"][0]["message"]["content"]
