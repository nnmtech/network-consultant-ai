#!/usr/bin/env python3
import asyncio
import time
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
import httpx

app = typer.Typer(help="Network Consultant AI - Production Monitoring CLI")
console = Console()

@app.command()
def monitor(
    url: str = typer.Option("http://localhost:3000", help="API base URL"),
    watch: bool = typer.Option(False, "--watch", "-w", help="Continuously monitor"),
    interval: int = typer.Option(5, help="Refresh interval in seconds")
):
    """Monitor system health and metrics in real-time"""
    
    async def fetch_status():
        async with httpx.AsyncClient() as client:
            try:
                health = await client.get(f"{url}/health", timeout=5)
                metrics = await client.get(f"{url}/metrics", timeout=5)
                status = await client.get(f"{url}/system/status", timeout=5)
                
                return {
                    "health": health.json() if health.status_code == 200 else None,
                    "metrics": metrics.json() if metrics.status_code == 200 else None,
                    "status": status.json() if status.status_code == 200 else None,
                }
            except Exception as e:
                return {"error": str(e)}
    
    def create_dashboard(data: dict) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )
        
        if "error" in data:
            layout["header"].update(Panel(f"[red]ERROR: {data['error']}[/red]", title="Status"))
            return layout
        
        health = data.get("health", {})
        metrics = data.get("metrics", {})
        status = data.get("status", {})
        
        header_text = f"[green]● HEALTHY[/green] | Version: {health.get('version', 'unknown')} | Uptime: {health.get('uptime_seconds', 0)}s"
        layout["header"].update(Panel(header_text, title="Network Consultant AI"))
        
        table = Table(title="System Metrics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        cache_hits = metrics.get("cache_hits", 0)
        cache_misses = metrics.get("cache_misses", 0)
        hit_rate = metrics.get("cache_hit_rate", 0.0)
        
        table.add_row("Cache Hits", str(cache_hits))
        table.add_row("Cache Misses", str(cache_misses))
        table.add_row("Cache Hit Rate", f"{hit_rate:.1%}")
        table.add_row("Environment", status.get("environment", "unknown"))
        
        layout["body"].update(table)
        layout["footer"].update(Panel(f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}", style="dim"))
        
        return layout
    
    if watch:
        async def watch_loop():
            with Live(console=console, refresh_per_second=1) as live:
                while True:
                    data = await fetch_status()
                    dashboard = create_dashboard(data)
                    live.update(dashboard)
                    await asyncio.sleep(interval)
        
        try:
            asyncio.run(watch_loop())
        except KeyboardInterrupt:
            console.print("\n[yellow]Monitoring stopped[/yellow]")
    else:
        data = asyncio.run(fetch_status())
        console.print(create_dashboard(data))

@app.command()
def cache_stats(
    url: str = typer.Option("http://localhost:3000", help="API base URL"),
    detail: bool = typer.Option(False, help="Show detailed statistics")
):
    """Display cache performance statistics"""
    
    async def fetch_metrics():
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(f"{url}/metrics", timeout=5)
                return response.json() if response.status_code == 200 else None
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
                return None
    
    metrics = asyncio.run(fetch_metrics())
    if not metrics:
        return
    
    table = Table(title="Cache Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    for key, value in metrics.items():
        if isinstance(value, float):
            table.add_row(key, f"{value:.3f}")
        else:
            table.add_row(key, str(value))
    
    console.print(table)

@app.command()
def diagnose(
    url: str = typer.Option("http://localhost:3000", help="API base URL"),
    full: bool = typer.Option(False, help="Run full diagnostics")
):
    """Run system diagnostics"""
    
    async def run_diagnostics():
        checks = []
        async with httpx.AsyncClient() as client:
            endpoints = [
                ("/health", "Health Check"),
                ("/health/live", "Liveness Probe"),
                ("/health/ready", "Readiness Probe"),
                ("/health/startup", "Startup Probe"),
            ]
            
            for endpoint, name in endpoints:
                try:
                    start = time.time()
                    response = await client.get(f"{url}{endpoint}", timeout=5)
                    duration = (time.time() - start) * 1000
                    
                    checks.append({
                        "name": name,
                        "status": "✓ PASS" if response.status_code == 200 else "✗ FAIL",
                        "code": response.status_code,
                        "duration_ms": f"{duration:.0f}ms"
                    })
                except Exception as e:
                    checks.append({
                        "name": name,
                        "status": "✗ ERROR",
                        "code": "N/A",
                        "duration_ms": str(e)
                    })
        
        return checks
    
    results = asyncio.run(run_diagnostics())
    
    table = Table(title="Diagnostic Results")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Code", style="yellow")
    table.add_column("Duration", style="magenta")
    
    for result in results:
        status_style = "green" if "PASS" in result["status"] else "red"
        table.add_row(
            result["name"],
            f"[{status_style}]{result['status']}[/{status_style}]",
            str(result["code"]),
            result["duration_ms"]
        )
    
    console.print(table)
    
    all_passed = all("PASS" in r["status"] for r in results)
    if all_passed:
        console.print("\n[green]✓ All diagnostics passed[/green]")
    else:
        console.print("\n[red]✗ Some diagnostics failed[/red]")

if __name__ == "__main__":
    app()