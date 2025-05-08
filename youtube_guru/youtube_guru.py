import json
from datetime import datetime, timedelta
import yt_dlp
import pandas as pd
import yfinance as yf
import streamlit as st
import altair as alt

# import gemini libraries and tools for extracting structured data
from google import genai
from google.genai import types
from pydantic import BaseModel

# load environment variables
from dotenv import load_dotenv
load_dotenv()

# set up gemini
client = genai.Client()
model = "gemini-1.5-pro"


class Prediction(BaseModel):
    who: str
    company_or_asset_class: str
    symbol: str
    timestamp: str
    prediction: str


class VideoData(BaseModel):
    who: str
    background: str
    predictions: list[Prediction]

prompt = """
Analyze this video.

Extract who is making predictions in the video. Summarize their background.

Extract stock picks and predictions. Focus on:

Price targets for specific assets (e.g., company stock, indexes, crypto) with predicted value and timeframe.
Macro predictions (e.g., interest rates, recessions) with event and timeline.
Bullish/bearish sentiment on companies, sectors, or asset classes.
General market calls (e.g., index movements, bull/bear runs).
Event-driven forecasts (e.g., earnings, policy changes).
Risky or contrarian bets (e.g., high-volatility assets, against-consensus calls).

For each prediction:

Quote/summarize the prediction and the reason for the prediction, the associated company, stock or asset symbol if possible, and the timestamp of the prediction.
"""

st.title("YouTube Guru Analyzer")

youtube_url = st.text_input("Enter the YouTube URL")

if youtube_url:
    ydl_opts = {}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        # makes the info json-serializable
        video_details = ydl.sanitize_info(info)

        video_date = datetime.strptime(video_details['upload_date'], "%Y%m%d")
        end_date = video_date + timedelta(days=365)
        start_date_str = video_date.strftime("%Y-%m-%d")
        end_date_str = end_date.strftime("%Y-%m-%d")

        st.subheader(video_details['title'])
        st.subheader(start_date_str)
        st.image(video_details['thumbnail'])
        

    with st.spinner("Analyzing predictions...", show_time=True):

        response = client.models.generate_content(
            model=model,
            contents=types.Content(
                parts=[
                    types.Part(text=prompt),
                    types.Part(
                        file_data=types.FileData(file_uri=youtube_url)
                    )
                ]
            ),
            config=types.GenerateContentConfig(
                response_mime_type="application/json", response_schema=VideoData
            )
        )

    
        st.subheader(response.parsed.who)
        st.write(response.parsed.background)

        for prediction in response.parsed.predictions:
            st.subheader(f"{prediction.company_or_asset_class} - {prediction.symbol}")
            st.write(f"Discussed at: {prediction.timestamp}")
            st.write(prediction.prediction)
            
            if prediction.symbol:
                stock = yf.Ticker(prediction.symbol)

                history = stock.history(start=start_date_str, end=end_date_str, interval="1d")
                

                # Prepare data for chart
                chart_data = pd.DataFrame(history["Close"]).reset_index()
                chart_data.columns = ['Date', 'Close']  # Rename columns for clarity

                start_price = chart_data["Close"].iloc[0]  # First price
                end_price = chart_data["Close"].iloc[-1]   # Last price
                total_return = ((end_price / start_price) - 1) * 100

                # display metrics in two columns
                col1, col2 = st.columns(2)

                with col1:
                    st.metric(label="Start Price", value=round(start_price, 2))

                with col2:
                    st.metric(label="1 Year Later", value=round(end_price, 2), delta=f"{total_return:.2f}%")

                # Create Altair chart
                chart = alt.Chart(chart_data).mark_line().encode(
                    x=alt.X('Date:T', axis=alt.Axis(format='%Y-%m-%d')),  # Full date format
                    y='Close:Q'
                ).properties(
                    width=600,
                    height=400
                )

                # Display in Streamlit
                st.altair_chart(chart, use_container_width=True)