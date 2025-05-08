from PIL import Image
import pytesseract
import sys

# Load the image
image_path = sys.argv[1]  #"/mnt/data/bbad519f2.jpg"
img = Image.open(image_path)

# Use Tesseract to extract text
text = pytesseract.image_to_string(img)
print(text)

