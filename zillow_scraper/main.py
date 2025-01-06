import logging
from scraper import ZillowScraper
from rich import print
from rich.console import Console
from rich.panel import Panel   
from rich.markdown import Markdown

import pandas as pd

def main():
    console = Console()
    logging.basicConfig(level=logging.INFO)
    data = []
    
    # zillow_url = "https://www.zillow.com/homes/for_rent/?searchQueryState=%7B%22isMapVisible%22%3Atrue%2C%22mapBounds%22%3A%7B%22west%22%3A-117.65486165545578%2C%22east%22%3A-117.54568501971359%2C%22south%22%3A33.578840547760386%2C%22north%22%3A33.671464800106676%7D%2C%22filterState%22%3A%7B%22fr%22%3A%7B%22value%22%3Atrue%7D%2C%22fsba%22%3A%7B%22value%22%3Afalse%7D%2C%22fsbo%22%3A%7B%22value%22%3Afalse%7D%2C%22nc%22%3A%7B%22value%22%3Afalse%7D%2C%22cmsn%22%3A%7B%22value%22%3Afalse%7D%2C%22auc%22%3A%7B%22value%22%3Afalse%7D%2C%22fore%22%3A%7B%22value%22%3Afalse%7D%2C%22baths%22%3A%7B%22min%22%3A1%7D%2C%22beds%22%3A%7B%22min%22%3A3%7D%2C%22mp%22%3A%7B%22max%22%3A4500%7D%2C%22price%22%3A%7B%22max%22%3A874592%7D%7D%2C%22isListVisible%22%3Atrue%2C%22usersSearchTerm%22%3A%22%22%2C%22customRegionId%22%3A%22745de677aeX1-CR1ofiabx0jkc0f_1b7nl4%22%2C%22pagination%22%3A%7B%7D%2C%22mapZoom%22%3A13%7D"  # Replace with your specific URL
    zillow_url = "https://www.zillow.com/homes/for_rent/2_p/?searchQueryState=%7B%22isMapVisible%22%3Atrue%2C%22mapBounds%22%3A%7B%22west%22%3A-117.90333265953402%2C%22east%22%3A-117.46662611656527%2C%22south%22%3A33.369778146629244%2C%22north%22%3A33.74057466204011%7D%2C%22filterState%22%3A%7B%22fr%22%3A%7B%22value%22%3Atrue%7D%2C%22fsba%22%3A%7B%22value%22%3Afalse%7D%2C%22fsbo%22%3A%7B%22value%22%3Afalse%7D%2C%22nc%22%3A%7B%22value%22%3Afalse%7D%2C%22cmsn%22%3A%7B%22value%22%3Afalse%7D%2C%22auc%22%3A%7B%22value%22%3Afalse%7D%2C%22fore%22%3A%7B%22value%22%3Afalse%7D%2C%22baths%22%3A%7B%22min%22%3A1%7D%2C%22beds%22%3A%7B%22min%22%3A3%7D%2C%22mp%22%3A%7B%22max%22%3A4500%7D%2C%22price%22%3A%7B%22max%22%3A874592%7D%2C%22sort%22%3A%7B%22value%22%3A%22paymenta%22%7D%7D%2C%22isListVisible%22%3Atrue%2C%22mapZoom%22%3A11%2C%22customRegionId%22%3A%226ebb1677b3X1-CR78pixfx4qer4_qj6dn%22%2C%22pagination%22%3A%7B%22currentPage%22%3A2%7D%2C%22usersSearchTerm%22%3A%22%22%7D"
    
    try:
        with ZillowScraper() as scraper:
            properties = scraper.scrape_rentals(zillow_url)
            
            for prop in properties:
                if prop.square_feet:
                    prop.price_per_sqft = round(prop.price_per_month / prop.square_feet, 2)
                md = f"""## {prop.address}\n
                Price: ${prop.price_per_month:,.2f}/month
                Priceer sq ft:** ${prop.price_per_sqft:.2f}
                Bedrooms: {prop.bedrooms}
                Bathrooms: {prop.bathrooms}
                Listed: {prop.listing_date}
                Neighborhood: {prop.neighborhood}\n
                URL: {prop.link}
                """
                console.print(Panel(Markdown(md), title="Property Details", expand=False), justify="center", style="bold green")

                # print("\nProperty Details:")
                # print(f"Address: {prop.address}")
                # print(f"Price: ${prop.price_per_month:,.2f}/month")
                # print(f"Bedrooms: {prop.bedrooms}")
                # print(f"Bathrooms: {prop.bathrooms}")
                # print(f"Neighborhood: {prop.neighborhood}")
                # print(f"URL: {prop.link}")
                # if prop.square_feet:
                #     print(f"Square Feet: {prop.square_feet:,.0f}")
                # if prop.price_per_sqft:
                #     print(f"Price per sq ft: ${prop.price_per_sqft:.2f}")
                # print(f"Listed: {prop.listing_date}")
                
            data.append(dict(prop))
    except Exception as e:
        logging.error(f"Error in main: {e}")
    df = pd.DataFrame(data)
    df.to_csv('property_details.csv', index=False)
    print(df)

if __name__ == "__main__":
    main()
