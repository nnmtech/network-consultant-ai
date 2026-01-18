from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import Response
from typing import Dict, Any, Optional
import structlog

from backend.export.report_generator import report_generator
from backend.auth.jwt_handler import verify_token
from backend.database.audit_logger import audit_logger

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/export", tags=["export"])

@router.post("/report/{request_id}")
async def export_report(
    request_id: str,
    format: str = Query(..., regex="^(pdf|docx|xlsx|csv|png|jpeg|json|html|markdown)$"),
    template: Optional[str] = None
):
    """
    Export orchestration report in specified format.
    
    Supported formats:
    - pdf: PDF document
    - docx: Microsoft Word document
    - xlsx: Microsoft Excel spreadsheet
    - csv: CSV file
    - png: PNG image
    - jpeg: JPEG image
    - json: JSON data
    - html: HTML page
    - markdown: Markdown document
    """
    try:
        # Fetch the orchestration result (from cache or database)
        # For now, using mock data - implement actual data fetching
        data = await _fetch_orchestration_data(request_id)
        
        if not data:
            raise HTTPException(status_code=404, detail="Request not found")
        
        # Generate report
        content = report_generator.generate_report(data, format, template)
        
        # Set appropriate content type and filename
        content_types = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "csv": "text/csv",
            "png": "image/png",
            "jpeg": "image/jpeg",
            "json": "application/json",
            "html": "text/html",
            "markdown": "text/markdown"
        }
        
        filename = f"network_report_{request_id}.{format}"
        
        logger.info(
            "report_exported",
            request_id=request_id,
            format=format,
            size_bytes=len(content)
        )
        
        return Response(
            content=content,
            media_type=content_types[format],
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Missing required library: {str(e)}"
        )
    except Exception as e:
        logger.error("export_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

@router.post("/batch")
async def batch_export(
    request_ids: list[str],
    format: str = Query(..., regex="^(pdf|docx|xlsx|csv|png|jpeg|json|html|markdown)$")
):
    """
    Export multiple reports at once.
    Returns a ZIP file containing all reports.
    """
    try:
        import zipfile
        import io
        
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for request_id in request_ids:
                try:
                    data = await _fetch_orchestration_data(request_id)
                    if data:
                        content = report_generator.generate_report(data, format)
                        filename = f"report_{request_id}.{format}"
                        zip_file.writestr(filename, content)
                except Exception as e:
                    logger.error("batch_export_item_failed", request_id=request_id, error=str(e))
        
        zip_buffer.seek(0)
        
        return Response(
            content=zip_buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename=network_reports.zip"
            }
        )
        
    except Exception as e:
        logger.error("batch_export_failed", error=str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Batch export failed: {str(e)}")

@router.get("/formats")
async def list_formats():
    """
    List all supported export formats.
    """
    return {
        "supported_formats": report_generator.supported_formats,
        "format_details": {
            "pdf": {"type": "document", "description": "Portable Document Format"},
            "docx": {"type": "document", "description": "Microsoft Word Document"},
            "xlsx": {"type": "spreadsheet", "description": "Microsoft Excel Spreadsheet"},
            "csv": {"type": "data", "description": "Comma-Separated Values"},
            "png": {"type": "image", "description": "PNG Image"},
            "jpeg": {"type": "image", "description": "JPEG Image"},
            "json": {"type": "data", "description": "JSON Data"},
            "html": {"type": "web", "description": "HTML Document"},
            "markdown": {"type": "document", "description": "Markdown Document"}
        }
    }

async def _fetch_orchestration_data(request_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch orchestration data from database or cache.
    This is a mock implementation - replace with actual data fetching.
    """
    # Mock data for demonstration
    return {
        "request_id": request_id,
        "client_issue": "Users experiencing slow network performance in Building A",
        "priority": "high",
        "confidence": 0.92,
        "consensus": "Network congestion detected due to misconfigured QoS settings and bandwidth saturation",
        "red_flagged": True,
        "recommendations": [
            "Implement QoS policies to prioritize critical traffic",
            "Upgrade uplink bandwidth from 1Gbps to 10Gbps",
            "Configure traffic shaping on edge routers",
            "Monitor bandwidth utilization hourly for next 7 days"
        ],
        "agents": {
            "Network Analyst": {
                "analysis": "Identified bandwidth saturation on uplink during peak hours (9AM-5PM). Current utilization reaches 95%."
            },
            "Security Auditor": {
                "analysis": "No security issues detected. Traffic patterns appear normal and legitimate."
            },
            "AD Specialist": {
                "analysis": "No Active Directory authentication delays. Issue is network-layer related."
            },
            "Compliance Checker": {
                "analysis": "Current configuration violates QoS best practices per company policy."
            }
        }
    }