document.addEventListener('DOMContentLoaded', () => {
    console.log("User Management Table Loaded");
});

// --- SORTING FUNCTION ---
function sortTable(n) {
    var table, rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
    table = document.getElementById("userTable");
    switching = true;
    dir = "asc"; // Set sort direction to ascending initially
    
    while (switching) {
        switching = false;
        rows = table.rows;
        
        // Loop through all table rows (excluding the header)
        for (i = 1; i < (rows.length - 1); i++) {
            shouldSwitch = false;
            
            // Compare current row and next row
            x = rows[i].getElementsByTagName("TD")[n];
            y = rows[i + 1].getElementsByTagName("TD")[n];
            
            var xContent = x.innerText.toLowerCase();
            var yContent = y.innerText.toLowerCase();

            if (dir == "asc") {
                if (xContent > yContent) {
                    shouldSwitch = true;
                    break;
                }
            } else if (dir == "desc") {
                if (xContent < yContent) {
                    shouldSwitch = true;
                    break;
                }
            }
        }
        
        if (shouldSwitch) {
            rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
            switching = true;
            switchcount ++; 
        } else {
            if (switchcount == 0 && dir == "asc") {
                dir = "desc";
                switching = true;
            }
        }
    }
}

// --- FILTERING FUNCTION ---
function filterTable() {
    var input, filter, table, tr, td, i, txtValue;
    input = document.getElementById("selectionFilter");
    filter = input.value.toUpperCase();
    table = document.getElementById("userTable");
    tr = table.getElementsByTagName("tr");

    // Loop through rows
    for (i = 1; i < tr.length; i++) {
        // Index 4 is "Selection" column
        td = tr[i].getElementsByTagName("td")[4]; 
        
        if (td) {
            txtValue = td.textContent || td.innerText;
            
            // If filter is ALL or matches the text
            if (filter === "ALL" || txtValue.toUpperCase().indexOf(filter) > -1) {
                tr[i].style.display = "";
            } else {
                tr[i].style.display = "none";
            }
        } 
    }
}