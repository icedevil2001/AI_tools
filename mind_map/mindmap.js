document.addEventListener('DOMContentLoaded', function() {
    const margin = {top: 20, right: 90, bottom: 30, left: 90},
        width = 1200 - margin.left - margin.right,
        height = 800 - margin.top - margin.bottom;

    let i = 0,
        duration = 750,
        root;

    const svg = d3.select("#tree").append("svg")
        .attr("width", width + margin.right + margin.left)
        .attr("height", height + margin.top + margin.bottom)
      .append("g")
        .attr("transform", "translate(" + margin.left + "," + margin.top + ")");

    const treemap = d3.tree().size([height, width]);

    // Load the JSON data
    d3.json("mindmap_data.json").then(function(treeData) {
        root = d3.hierarchy(treeData, function(d) { return d.children; });
        root.x0 = height / 2;
        root.y0 = 0;

        // Collapse after the first level
        root.children.forEach(collapse);

        update(root);
    });

    function collapse(d) {
        if(d.children) {
            d._children = d.children;
            d._children.forEach(collapse);
            d.children = null;
        }
    }

    function update(source) {
        const treeData = treemap(root);

        const nodes = treeData.descendants().reverse();
        const links = treeData.links();

        nodes.forEach(function(d){ d.y = d.depth * 180 }); // Adjust depth spacing

        const node = svg.selectAll("g.node")
            .data(nodes, function(d) { return d.id || (d.id = ++i); });

        const nodeEnter = node.enter().append("g")
            .attr("class", "node")
            .attr("transform", function(d) {
                return "translate(" + source.y0 + "," + source.x0 + ")";
            })
            .on("click", click);

        nodeEnter.append("circle")
            .attr("r", 1e-6)
            .style("fill", function(d) { return d._children ? "lightsteelblue" : "#fff"; });

        nodeEnter.append("text")
            .attr("dy", ".35em")
            .attr("x", function(d) { return d.children || d._children ? -13 : 13; })
            .attr("text-anchor", function(d) { return d.children || d._children ? "end" : "start"; })
            .text(function(d) { return d.data.name; });

        const nodeUpdate = nodeEnter.merge(node);

        nodeUpdate.transition()
            .duration(duration)
            .attr("transform", function(d) {
                return "translate(" + d.y + "," + d.x + ")";
            });

        nodeUpdate.select("circle")
            .attr("r", 10)
            .style("fill", function(d) { return d._children ? "lightsteelblue" : "#fff"; })
            .attr("cursor", "pointer");

        const nodeExit = node.exit().transition()
            .duration(duration)
            .attr("transform", function(d) {
                return "translate(" + source.y + "," + source.x + ")";
            })
            .remove();

        nodeExit.select("circle")
            .attr("r", 1e-6);

        nodeExit.select("text")
            .style("fill-opacity", 1e-6);

        const link = svg.selectAll("path.link")
            .data(links, function(d) { return d.id; });

        const linkEnter = link.enter().insert("path", "g")
            .attr("class", "link")
            .attr("d", function(d){ return diagonal(d, d.parent); });

        const linkUpdate = linkEnter.merge(link);

        linkUpdate.transition()
            .duration(duration)
            .attr("d", function(d){ return diagonal(d, d.parent); });

        link.exit().transition()
            .duration(duration)
            .attr("d", function(d) { return diagonal(d, source); })
            .remove();

        nodes.forEach(function(d) {
            d.x0 = d.x;
            d.y0 = d.y;
        });
    }

    function diagonal(s, d) {
        const path = `M ${s.y},${s.x}
                C ${(s.y + d.y) / 2},${s.x}
                  ${(s.y + d.y) / 2},${d.x}
                  ${d.y},${d.x}`;
        return path;
    }

    function click(event, d) {
        if (d.data.file) {
            // Simulate linking to the document by showing an alert with the filename.
            // In a real application, you would implement logic here to display the document content.
            alert("Linking to file: " + d.data.file);
        }

        if (d.children) {
            d._children = d.children;
            d.children = null;
        } else {
            d.children = d._children;
            d._children = null;
        }
        update(d);
    }

    // Functions for persistence and adding new files (require additional implementation)

    // Placeholder for adding new files
    function addFiles() {
        alert("Add Files functionality requires additional implementation (e.g., a server-side script) to process new files and update the mind map data.");
        // To implement this, you would need to:
        // 1. Handle file input (e.g., from an <input type="file"> element).
        // 2. Parse the new file(s) to extract relevant information.
        // 3. Update the 'treeData' object with the new document information.
        // 4. Re-render the mind map by calling update(root) or a similar function.
    }

    // Placeholder for saving the mind map
    function saveMindMap() {
        alert("Save Mind Map functionality requires additional implementation (e.g., using browser's local storage or a server-side script) to save the mind map data.");
        // To implement this, you could:
        // 1. Convert the 'treeData' object to a JSON string.
        // 2. Save the JSON string to the browser's local storage (for client-side persistence)
        //    or send it to a server to be saved in a file or database.
        const dataToSave = JSON.stringify(treeData, null, 4);
        console.log("Mind Map Data to Save:", dataToSave); // You can copy this from the browser's console
        // Example using local storage:
        // localStorage.setItem("mindMapData", dataToSave);
    }
});