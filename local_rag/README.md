# Local RAG Application

This is a Streamlit application that allows you to run the RAG model locally on your machine. 


### Prerequisites 
    - [Ollama](https://ollama.dev/download)
    - python >3.10
    - SQLite > 3.35

### Ollama models
After installing Ollama, you can run the following commands to install the required models:

```sh 
ollama run llama3.2 
ollama run nomic-embed-text 
```

### Running the application
To run the application, you can use the following command:

```sh
streamlit run app.py
```

### Optional 
#### Install uv 
For a more consistent development environment, you can use `uv` to create a virtual environment. How to create a virtual environment using `uv`: https://earthly.dev/blog/python-uv/ 
```sh
## MacOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

## Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```
#### uv create and activate environment
```sh
uv venv --python 3.11
uv sync

source .venv/bin/activate
```
----


## 🔧 Common Issues and Fixes

- If you run into any errors with incompatible version of ChromaDB/Sqlite3, refer to [this solution](https://docs.trychroma.com/troubleshooting#sqlite).