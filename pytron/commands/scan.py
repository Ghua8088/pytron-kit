import argparse
from pathlib import Path
from ..console import console, log, Rule
from ..pack.graph import GraphBuilder, DependencyOracle


def cmd_scan(args: argparse.Namespace) -> int:
    """
    Runs the 'Oracle Scan' on a target project.
    Visualizes insights without building.
    """
    target = args.target if args.target else "."
    project_path = Path(target).resolve()

    if not project_path.exists():
        log(f"Path not found: {project_path}", style="error")
        return 1

    console.print(Rule("[bold magenta]Pytron Dependency Oracle"))
    console.print(f"Scanning target: [cyan]{project_path}[/cyan]")

    # 1. Build Graph
    try:
        builder = GraphBuilder(project_path)
        graph = builder.scan_project()
    except Exception as e:
        log(f"Scan failed: {e}", style="error")
        return 1

    console.print(f"  Nodes: [bold]{len(graph.nodes)}[/bold]")
    console.print(f"  Edges: [bold]{len(graph.edges)}[/bold]")
    console.print(
        f"  Uncertainty Zones: [bold red]{len(graph._uncertainty_zones)}[/bold red]"
    )

    # 2. Run Oracle
    console.print(Rule("[bold yellow]Connecting to Brain..."))
    oracle = DependencyOracle(graph)
    oracle.predict()

    # 3. Report Results
    predictions = [e for e in graph.edges if e.type == "predicted"]

    if predictions:
        console.print(
            f"Oracle made [bold green]{len(predictions)}[/bold green] inference(s):"
        )
        for pred in predictions:
            confidence_style = "green" if pred.confidence > 0.8 else "yellow"
            console.print(
                f"  Ref: [cyan]{pred.source}[/cyan] -> [bold {confidence_style}]{pred.target}[/bold {confidence_style}]"
            )
            console.print(f"  Reason: [dim]{pred.reason}[/dim]")
            console.print("")
    else:
        console.print(
            "[dim]No dynamic anomalies detected. Standard build should suffice.[/dim]"
        )

    # 4. Show Uncertainty Zones (if unpredicted)
    # Filter zones that didn't result in a prediction?
    # For now, just show them all
    if args.verbose and graph._uncertainty_zones:
        console.print(Rule("[bold red]Uncertainty Zones"))
        for zone in graph._uncertainty_zones:
            console.print(f"[red]![/red] {zone['source']}:{zone['lineno']}")
            console.print(f"    Code: `{zone['code']}`")
            console.print(f"    Type: {zone['heuristic']}")
            console.print("")

    # 5. Export
    if args.json:
        out_file = project_path / "scan_report.json"
        out_file.write_text(graph.to_json(), encoding="utf-8")
        log(f"Report saved to {out_file}", style="success")

    if getattr(args, "html", False):
        html_path = project_path / "scan_graph.html"
        generate_interactive_graph(graph, html_path)
        log(f"Visual Graph saved to {html_path}", style="success")

    return 0


def generate_interactive_graph(graph, out_path: Path):
    """Generates a standalone HTML D3.js graph."""
    import json

    data = json.loads(graph.to_json())

    # Simple D3 Template
    html = """
<!DOCTYPE html>
<html>
<head>
    <style> 
        body { margin: 0; background: #111; color: #eee; font-family: sans-serif; overflow: hidden; } 
        #graph { width: 100vw; height: 100vh; }
        .node { stroke: #fff; stroke-width: 1.5px; }
        .link { stroke: #555; stroke-opacity: 0.6; }
        text { font-size: 10px; fill: #ccc; pointer-events: none; }
        .tooltip { position: absolute; background: #333; padding: 5px; border: 1px solid #777; border-radius: 4px; display: none; }
    </style>
    <script src="https://d3js.org/d3.v7.min.js"></script>
</head>
<body>
    <div id="graph"></div>
    <div class="tooltip" id="tooltip"></div>
    <script>
        const data = __GRAPH_DATA__;
        
        const width = window.innerWidth;
        const height = window.innerHeight;
        
        // Convert map to array
        const nodes = Object.values(data.nodes).map(n => ({id: n.name, type: n.type}));
        const links = data.edges.map(e => ({source: e.source, target: e.target, type: e.type, conf: e.confidence}));
        
        const svg = d3.select("#graph").append("svg")
            .attr("width", width)
            .attr("height", height)
            .call(d3.zoom().on("zoom", (event) => {
                g.attr("transform", event.transform);
            }));
            
        const g = svg.append("g");
        
        const simulation = d3.forceSimulation(nodes)
            .force("link", d3.forceLink(links).id(d => d.id).distance(100))
            .force("charge", d3.forceManyBody().strength(-300))
            .force("center", d3.forceCenter(width / 2, height / 2));
            
        const link = g.append("g")
            .attr("class", "links")
            .selectAll("line")
            .data(links)
            .enter().append("line")
            .attr("class", "link")
            .attr("stroke", d => d.type === "predicted" ? "#0f0" : "#555")
            .attr("stroke-dasharray", d => d.type === "predicted" ? "5,5" : "0")
            .attr("stroke-width", d => Math.max(1, d.conf * 3));

        const node = g.append("g")
            .attr("class", "nodes")
            .selectAll("circle")
            .data(nodes)
            .enter().append("circle")
            .attr("r", 5)
            .attr("fill", d => d.type === "package" ? "#f00" : "#00f")
            .call(d3.drag()
                .on("start", dragstarted)
                .on("drag", dragged)
                .on("end", dragended));

        const label = g.append("g")
            .selectAll("text")
            .data(nodes)
            .enter().append("text")
            .attr("dy", -10)
            .text(d => d.id);
            
        node.on("mouseover", (event, d) => {
            d3.select("#tooltip")
                .style("display", "block")
                .style("left", (event.pageX + 10) + "px")
                .style("top", (event.pageY - 10) + "px")
                .html(`<strong>${d.id}</strong><br>${d.type}`);
        }).on("mouseout", () => {
            d3.select("#tooltip").style("display", "none");
        });

        simulation.on("tick", () => {
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            node
                .attr("cx", d => d.x)
                .attr("cy", d => d.y);
                
            label
                .attr("x", d => d.x)
                .attr("y", d => d.y);
        });

        function dragstarted(event, d) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }

        function dragged(event, d) {
            d.fx = event.x;
            d.fy = event.y;
        }

        function dragended(event, d) {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }
    </script>
</body>
</html>
    """

    html = html.replace("__GRAPH_DATA__", json.dumps(data))
    out_path.write_text(html, encoding="utf-8")
