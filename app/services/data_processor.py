"""Data processing utilities"""

import io
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

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
        return [{f: DataProcessor.flatten(ad).get(f, "") for f in fields} for ad in ads]

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
        return {key.replace("-", "_"): value for key, value in s.items()}

    @staticmethod
    def calculate_ad_quality(ad: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate quality metadata for a single ad"""

        def count_fields(obj: Any, prefix: str = "") -> tuple[int, int]:
            """Count total fields and filled fields recursively"""
            total = 0
            filled = 0

            if isinstance(obj, dict):
                for key, value in obj.items():
                    if isinstance(value, (dict, list)):
                        sub_total, sub_filled = count_fields(value, f"{prefix}.{key}")
                        total += sub_total
                        filled += sub_filled
                    else:
                        total += 1
                        if value is not None and value != "":
                            filled += 1
            elif isinstance(obj, list):
                for item in obj:
                    sub_total, sub_filled = count_fields(item, prefix)
                    total += sub_total
                    filled += sub_filled

            return total, filled

        def get_missing_fields(obj: Any, prefix: str = "") -> List[str]:
            """Get list of empty/missing fields"""
            missing = []

            if isinstance(obj, dict):
                for key, value in obj.items():
                    field_path = f"{prefix}.{key}" if prefix else key
                    if isinstance(value, (dict, list)):
                        missing.extend(get_missing_fields(value, field_path))
                    elif value is None or value == "":
                        missing.append(field_path)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    missing.extend(get_missing_fields(item, f"{prefix}[{i}]"))

            return missing

        total_fields, filled_fields = count_fields(ad)
        completeness = (filled_fields / total_fields * 100) if total_fields > 0 else 0

        return {
            "ad_id": ad.get("id", "unknown"),
            "completeness_score": round(completeness, 2),
            "missing_fields": get_missing_fields(ad),
            "quality_issues": [],
            "data_structure": {
                "total_fields": total_fields,
                "filled_fields": filled_fields,
                "field_completeness": round(completeness, 2),
            },
        }

    @staticmethod
    def calculate_database_metadata(
        ads: List[Dict[str, Any]], total_count: int = None
    ) -> Dict[str, Any]:
        """Calculate overall database metadata from a sample of ads"""
        if not ads:
            return {
                "total_ads": total_count or 0,
                "date_range": {"min_date": None, "max_date": None},
                "field_metadata": [],
                "average_completeness": 0,
                "data_quality_summary": {},
                "last_updated": datetime.now().isoformat(),
            }

        # Collect all field completeness scores
        quality_scores = [
            DataProcessor.calculate_ad_quality(ad)["completeness_score"] for ad in ads
        ]
        avg_completeness = sum(quality_scores) / len(quality_scores) if quality_scores else 0

        # Extract date range
        dates = []
        for ad in ads:
            for date_field in ["publication_date", "published_date", "created_at"]:
                if date_field in ad and ad[date_field]:
                    dates.append(str(ad[date_field]))
                    break

        date_range = {
            "min_date": min(dates) if dates else None,
            "max_date": max(dates) if dates else None,
            "sample_size": len(ads),
        }

        # Build field-level metadata
        field_stats: Dict[str, Dict[str, Any]] = {}
        for ad in ads:
            flattened = DataProcessor.flatten(ad)
            for field, value in flattened.items():
                if field not in field_stats:
                    field_stats[field] = {
                        "total": 0,
                        "filled": 0,
                        "samples": set(),
                        "type": type(value).__name__,
                    }
                field_stats[field]["total"] += 1
                if value is not None and value != "":
                    field_stats[field]["filled"] += 1
                    if len(field_stats[field]["samples"]) < 3:
                        field_stats[field]["samples"].add(str(value)[:50])

        field_metadata = [
            {
                "field_name": field,
                "data_type": stats["type"],
                "completeness": round(stats["filled"] / stats["total"] * 100, 2)
                if stats["total"] > 0
                else 0,
                "total_records": stats["total"],
                "filled_records": stats["filled"],
                "sample_values": list(stats["samples"])[:3],
            }
            for field, stats in sorted(field_stats.items())
        ]

        return {
            "total_ads": total_count or len(ads),
            "date_range": date_range,
            "field_metadata": field_metadata,
            "average_completeness": round(avg_completeness, 2),
            "data_quality_summary": {
                "fields_analyzed": len(field_stats),
                "highly_complete_fields": sum(1 for f in field_metadata if f["completeness"] >= 80),
                "incomplete_fields": sum(1 for f in field_metadata if f["completeness"] < 50),
                "quality_distribution": {
                    "excellent": sum(1 for s in quality_scores if s >= 90),
                    "good": sum(1 for s in quality_scores if 70 <= s < 90),
                    "acceptable": sum(1 for s in quality_scores if 50 <= s < 70),
                    "poor": sum(1 for s in quality_scores if s < 50),
                },
            },
            "last_updated": datetime.now().isoformat(),
        }


# Singleton
_processor: Optional[DataProcessor] = None


def get_processor() -> DataProcessor:
    """Get processor instance"""
    global _processor
    if _processor is None:
        _processor = DataProcessor()
    return _processor
