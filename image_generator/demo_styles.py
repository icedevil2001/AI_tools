#!/usr/bin/env python3
"""
Demo script showing the new image styles from imagestyles.ai
"""
import main

def demo_styles():
    """Demonstrate some of the new styles available."""
    print("🎨 AI Image Generator - Now with 80+ Image Styles from imagestyles.ai!")
    print("=" * 60)
    
    print("\n📋 Available Style Categories:")
    
    # Group styles by category for better display
    categories = {
        "🎮 Gaming Styles": [
            "grand-theft-auto-v", "valorant", "mario-n64", "pokemon", 
            "animal-crossing", "hollow-knight", "monument-valley"
        ],
        "📺 Animation Styles": [
            "studio-ghibli", "rick-and-morty", "simpsons", "south-park",
            "anime", "manga", "muppets", "spongebob"
        ],
        "🎨 Art Styles": [
            "watercolor", "oil-on-canvas", "pop-art", "picasso", 
            "pixel-art", "ascii-art", "minimalistic"
        ],
        "🎪 Digital Effects": [
            "8-bit", "voxels", "low-poly", "3d", "cel-shading", 
            "claymation", "lego"
        ],
        "📸 Photography": [
            "polaroid", "wet-plate-collodion", "western"
        ]
    }
    
    for category, styles in categories.items():
        print(f"\n{category}:")
        for style in styles:
            description = main.IMAGE_STYLES.get(style, "No description")
            print(f"  • {style}: {description}")
    
    print(f"\n🔢 Total Styles Available: {len(main.IMAGE_STYLES)}")
    print("\n🔗 All styles with visual examples: https://imagestyles.ai")
    print("\n🚀 To try these styles:")
    print("   1. Run: uv run python main.py")
    print("   2. Select any style from the dropdown")
    print("   3. Watch the style description update automatically")
    print("   4. Generate images with that artistic style applied!")
    
    print("\n✨ Example Usage:")
    print("   • Choose 'studio-ghibli' style")
    print("   • Enter prompt: 'a magical forest with floating islands'")
    print("   • Result: Your prompt + ' in Studio Ghibli animation style'")

if __name__ == "__main__":
    demo_styles()
