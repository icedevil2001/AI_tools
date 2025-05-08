"""
Utility functions for tracking and calculating API costs
"""

import time
from dataclasses import dataclass
from typing import List, Dict, Optional

# Current Gemini API pricing (as of 2024)
PRICING = {
    "gemini-2.0-flash": {
        "input": 0.000003,  # $0.000003 per 1K input tokens
        "output": 0.000006  # $0.000006 per 1K output tokens
    },
    "gemini-2.0-pro": {
        "input": 0.000012,  # $0.000012 per 1K input tokens
        "output": 0.000024  # $0.000024 per 1K output tokens
    }
}

# Default model to use for pricing calculations
DEFAULT_MODEL = "gemini-2.0-flash"

@dataclass
class ApiRequest:
    """Represents a single API request"""
    request_type: str  # 'transcription', 'summary', or 'qa'
    model: str
    input_tokens: int
    output_tokens: int
    timestamp: float
    
    @property
    def total_tokens(self):
        return self.input_tokens + self.output_tokens
    
    @property
    def cost(self):
        model_pricing = PRICING.get(self.model, PRICING[DEFAULT_MODEL])
        input_cost = (self.input_tokens / 1000) * model_pricing["input"]
        output_cost = (self.output_tokens / 1000) * model_pricing["output"]
        return input_cost + output_cost

class ApiCostTracker:
    """Track API costs for a session"""
    
    def __init__(self):
        self.requests: List[ApiRequest] = []
    
    def add_request(self, request_type: str, model: str, 
                   input_tokens: int, output_tokens: int) -> float:
        """Add a request to the tracker and return its cost"""
        request = ApiRequest(
            request_type=request_type,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            timestamp=time.time()
        )
        self.requests.append(request)
        return request.cost
    
    @property
    def total_tokens(self) -> int:
        """Get the total number of tokens used"""
        return sum(req.total_tokens for req in self.requests)
    
    @property
    def total_cost(self) -> float:
        """Get the total cost of all requests"""
        return sum(req.cost for req in self.requests)
    
    def get_request_count_by_type(self) -> Dict[str, int]:
        """Get count of requests by type"""
        counts = {}
        for req in self.requests:
            counts[req.request_type] = counts.get(req.request_type, 0) + 1
        return counts
    
    def get_summary(self) -> Dict:
        """Get a complete summary of usage and costs"""
        request_summary = []
        for req in self.requests:
            request_summary.append({
                "type": req.request_type,
                "model": req.model,
                "input_tokens": req.input_tokens,
                "output_tokens": req.output_tokens,
                "total_tokens": req.total_tokens,
                "cost": req.cost,
                "timestamp": req.timestamp
            })
        
        return {
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "requests": request_summary,
            "request_counts": self.get_request_count_by_type()
        }
