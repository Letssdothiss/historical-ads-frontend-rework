"""Data processing utilities"""
import io
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd


class DataProcessor:
    """Process and transform job ad data"""
    
    DEFAULT_FIELDS = [
        "id",
        "original_id", 
        "headline",
        "publication_date",
        "application_deadline",
        "number_of_vacancies",
        "employer.name",
        "workplace_address.municipality",
        "workplace_address.region",
        "occupation.label",
        "occupation_group.label",
        "occupation_field.label",
        "employment_type.label",
        "duration.label",
        "working_hours_type.label",
    ]
    
    @staticmethod
    def flatten(ad: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """Flatten nested dictionary"""
        result = {}
        for key, value in ad.items():
            new_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                result.update(DataProcessor.flatten(value, new_key))
            elif isinstance(value, list):
                if value and isinstance(value[0], dict):
                    result[new_key] = json.dumps(value)
                else:
                    result[new_key] = ", ".join(str(v) for v in value)
            else:
                result[new_key] = value
        return result
    
    @staticmethod
    def extract(ads: List[Dict], fields: List[str]) -> List[Dict]:
        """Extract specified fields from ads"""
        return [
            {f: DataProcessor.flatten(ad).get(f, "") for f in fields}
            for ad in ads
        ]
    
    def to_json(self, ads: List[Dict], fields: Optional[List[str]] = None) -> str:
        """Export to JSON"""
        if fields:
            ads = self.extract(ads, fields)
        return json.dumps(ads, indent=2, ensure_ascii=False, default=str)
    
    def to_csv(self, ads: List[Dict], fields: Optional[List[str]] = None) -> str:
        """Export to CSV"""
        if not ads:
            return ""
        fields = fields or self.DEFAULT_FIELDS
        data = self.extract(ads, fields)
        df = pd.DataFrame(data)
        return df.to_csv(index=False)
    
    def to_xlsx(self, ads: List[Dict], fields: Optional[List[str]] = None) -> bytes:
        """Export to Excel"""
        fields = fields or self.DEFAULT_FIELDS
        data = self.extract(ads, fields) if ads else []
        df = pd.DataFrame(data)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Annonser", index=False)
        
        return output.getvalue()
    
    @staticmethod
    def filename(query: Optional[str] = None, ext: str = "json") -> str:
        """Generate export filename"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if query:
            safe = "".join(c if c.isalnum() or c in " -_" else "" for c in query)
            safe = safe[:50].strip().replace(" ", "_")
            return f"annonser_{safe}_{ts}.{ext}"
        return f"annonser_{ts}.{ext}"
    
    @staticmethod
    def extract_filters(stats: Dict) -> Dict[str, Any]:
        """Extract filter options from stats."""
        s = stats.get("stats", {})
        return {
            key.replace("-", "_"): value
            for key, value in s.items()
        }


# Singleton
_processor: Optional[DataProcessor] = None


def get_processor() -> DataProcessor:
    """Get processor instance"""
    global _processor
    if _processor is None:
        _processor = DataProcessor()
    return _processor