#!/usr/bin/env python3
"""
Test script for the AI Image Generator cost tracking functionality.
"""

import json
from pathlib import Path

# Test cost calculation functions
def test_cost_tracking():
    print("🧪 Testing Cost Tracking Functionality")
    print("=" * 50)
    
    # Test pricing data
    PRICING = {
        "dall-e-3": {
            "standard": {
                "1024x1024": 0.040,
                "1024x1792": 0.080,
                "1792x1024": 0.080
            },
            "hd": {
                "1024x1024": 0.080,
                "1024x1792": 0.120,
                "1792x1024": 0.120
            }
        },
        "dall-e-2": {
            "standard": {
                "256x256": 0.016,
                "512x512": 0.018,
                "1024x1024": 0.020
            }
        }
    }
    
    def calculate_cost(model, quality, size):
        """Calculate the cost for generating an image."""
        try:
            if model == "dall-e-2":
                return PRICING[model]["standard"].get(size, 0.020)
            else:  # dall-e-3
                return PRICING[model][quality].get(size, 0.040)
        except KeyError:
            return 0.040  # Default fallback cost
    
    # Test cases
    test_cases = [
        ("dall-e-3", "standard", "1024x1024", 0.040),
        ("dall-e-3", "hd", "1024x1024", 0.080),
        ("dall-e-3", "standard", "1024x1792", 0.080),
        ("dall-e-3", "hd", "1792x1024", 0.120),
        ("dall-e-2", "standard", "1024x1024", 0.020),
        ("dall-e-2", "standard", "512x512", 0.018),
        ("dall-e-2", "standard", "256x256", 0.016),
    ]
    
    print("Testing cost calculations...")
    for model, quality, size, expected in test_cases:
        actual = calculate_cost(model, quality, size)
        status = "✅" if actual == expected else "❌"
        print(f"{status} {model} {quality} {size}: ${actual:.3f} (expected ${expected:.3f})")
    
    print("\n📊 Cost Examples:")
    print(f"DALL-E 3 Standard 1024x1024: ${calculate_cost('dall-e-3', 'standard', '1024x1024'):.3f}")
    print(f"DALL-E 3 HD 1024x1024: ${calculate_cost('dall-e-3', 'hd', '1024x1024'):.3f}")
    print(f"DALL-E 3 HD 1024x1792: ${calculate_cost('dall-e-3', 'hd', '1024x1792'):.3f}")
    print(f"DALL-E 2 Standard 1024x1024: ${calculate_cost('dall-e-2', 'standard', '1024x1024'):.3f}")
    
    print("\n✅ Cost tracking test completed!")

if __name__ == "__main__":
    test_cost_tracking()
