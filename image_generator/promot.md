Write a Python script that creates an interactive web app using Gradio to generate images from text using a GPT-style image model (such as OpenAI's DALL·E and GPT-image-1 via the OpenAI API).
The script should:
Include a text input where the user can type a prompt (e.g., "a cat riding a motorcycle in space").
Send that prompt to the image generation API (OpenAI or equivalent).
Display the generated image directly in the Gradio interface.
Save the image locally.
Use the OpenAI Python SDK (or another image model API if OpenAI is not used).
Handle errors gracefully (e.g., failed image generation, empty prompts).
Bonus: Add options to choose image resolution and seed if supported by the API.