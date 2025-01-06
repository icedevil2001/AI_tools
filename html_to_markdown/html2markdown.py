
from typing import Any, Union
from bs4 import BeautifulSoup
import click  
import requests
from markitdown import MarkItDown
from openai import OpenAI
from rich import print
from rich.console import Console
from rich.panel import Panel  
from rich.text import Text
from rich.markdown import Markdown  
import re

client = OpenAI()

def ai_extract_recipe(context: str, llm_client: OpenAI) -> str:
    
    response = llm_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a Michelan Star chef. He will help to extract the recipe and the number of servings and any nutritional information that is presented. And respond in markdown. "},
            {"role": "user", "content": context},
            # {"role": "assistant", "content": result.text_content},
        ])
    return response.choices[0].message.content

def safe_title(title: str) -> str:
    return re.sub(r"[-\s+:]", "_", title)

def html2markdown(url: str, llm_client: OpenAI) -> str:
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.string

    md = MarkItDown()

    result = md.convert_url(url)
    return result.text_content, title




@click.command()
@click.option("--url", prompt="Enter the URL", help="The URL of the webpage to convert to markdown")
@click.option('--output', '-o', default=None, help="The output file name")
@click.option('--recipe', '-r', is_flag=True, help="Extract the recipe from the page")
def main(url: str, output: str, recipe: bool):

    result, title = html2markdown(url, client)
    if recipe:
        result = ai_extract_recipe(result, client)
    if output:
        with open(output, "w") as file:
            file.write(result)
        print(f"Markdown file saved as {output}")
    else:
        console = Console()
        console.print(
            Panel(
                Markdown(result), 
                title=title, 
                expand=True, 
                padding=(1, 2), 
                border_style="green")
            )
    

if __name__ == "__main__":
    main()

    # console = Console()
    # console.print(
    #     Panel(
    #         Markdown(result.text_content), 
    #         title=title, 
    #         expand=True, 
    #         padding=(1, 2), 
    #         border_style="green")
    #     )

    # safe_title_str = safe_title(title)
    # with open(f"{safe_title_str}.md", "w") as file:
    #     file.write(result.text_content)

    # print(f"Markdown file saved as {safe_title}.md")
    # return result.text_content

# url = "https://shaneandsimple.com/vegan-black-pepper-tofu/"

# response = requests.get(url)
# soup = BeautifulSoup(response.text, "html.parser")
# title = soup.title.string




## save html content to a file
# source = soup.prettify()
# tmp_filename = "source.html"
# with open(tmp_filename, "w") as file:
#     file.write(source)

## convert html to markdown
# print(help(MarkItDown))
# exit()
# md = MarkItDown()

# result = md.convert_url(url)

# console = Console()
# console.print(
#     Panel(
#         Markdown(result.text_content), 
#         title=title, 
#         expand=True, 
#         padding=(1, 2), 
#         border_style="green")
#     )

# safe_title_str = safe_title(title)
# with open(f"{safe_title_str}.md", "w") as file:
#     file.write(result.text_content)

# print(f"Markdown file saved as {safe_title}.md")

