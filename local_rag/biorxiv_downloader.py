import requests
import os
import json
from datetime import datetime
import time
import click


# import requests

# # Define the API endpoint
# base_url = "https://api.biorxiv.org/"

# # Fetch the latest 10 articles
# endpoint = "pub/new"
# response = requests.get(base_url + endpoint)

# if response.status_code == 200:
#     data = response.json()
#     # Process the data
#     for article in data['collection']:
#         print(article['title'])
# else:
#     print("Error: ", response.status_code)



class BiorxivDownloader:
    def __init__(self, output_dir="downloaded_papers", start_date="2000-01-01"):
        self.base_url = "https://api.biorxiv.org/details/biorxiv"
        self.output_dir = output_dir
        self.start_date = "2000-01-01"
        os.makedirs(output_dir, exist_ok=True)
        
    def search_papers(self, topic, start_date=None, end_date=None, max_results=10):
        """Search for papers on a specific topic"""
        if not start_date:
            start_date = "2000-01-01"
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
            
        url = f"{self.base_url}/{start_date}/{end_date}/{topic}"
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('collection', [])[:max_results]
        return []
    
    def download_paper(self, paper_info):
        """Download PDF for a single paper"""
        doi = paper_info.get('doi')
        if not doi:
            return False
            
        pdf_url = f"https://www.biorxiv.org/content/{doi}.full.pdf"
        response = requests.get(pdf_url)
        
        if response.status_code == 200:
            filename = f"{self.output_dir}/{doi.replace('/', '_')}.pdf"
            with open(filename, 'wb') as f:
                f.write(response.content)
            return True
        return False


@click.command()
@click.option("--topic", '-t', prompt="Enter search topic", help="Topic to search for")
@click.option("--max-results", '-m', default=10, help="Maximum number of papers to download")
@click.option("--output-dir", "-o", default="downloaded_papers", help="Directory to save downloaded papers")
@click.option("--start-date", "-s", default="2000-01-01", help="Start date for search")
@click.option("--end-date", "-e", default=datetime.now().strftime("%Y-%m-%d"), help="End date for search")
def main(topic, max_results, output_dir, start_date, end_date):
    downloader = BiorxivDownloader()
    # topic = input("Enter search topic: ")
    # max_results = int(input("Enter maximum number of papers to download (default 10): ") or 10)
    
    print(f"Searching for papers about {topic}...")
    papers = downloader.search_papers(
        topic, 
        start_date=start_date,
        end_date=end_date,
        max_results=max_results)
    
    if not papers:
        print("No papers found!")
        return
        
    print(f"Found {len(papers)} papers. Starting download...")
    
    for paper in papers:
        print(f"Downloading: {paper.get('title')}")
        if downloader.download_paper(paper):
            print("Success!")
            # Save metadata
            metadata_file = f"{downloader.output_dir}/{paper.get('doi').replace('/', '_')}.json"
            with open(metadata_file, 'w') as f:
                json.dump(paper, f, indent=2)
        else:
            print("Failed to download")
        time.sleep(1)  # Be nice to the server

if __name__ == "__main__":
    main()
