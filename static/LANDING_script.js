document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('mainChart');
    
    // Safety check: Only run if the chart canvas exists on the page
    if (!canvas) {
        console.warn("Main chart canvas not found.");
        return;
    }

    const ctx = canvas.getContext('2d');
    
    // Create gradient for a professional look
    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, '#3b82f6'); // Royal Blue
    gradient.addColorStop(1, '#60a5fa'); // Sky Blue

    // Initialize Chart.js
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4'],
            datasets: [{
                data: [5000, 7000, 5800, 7200],
                backgroundColor: gradient,
                borderRadius: 6,
                barThickness: 50
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { 
                legend: { display: false } 
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 8000,
                    ticks: {
                        stepSize: 2000,
                        // Formats numbers as Singapore Dollars
                        callback: value => 'S$' + value.toLocaleString()
                    },
                    grid: { 
                        borderDash: [5, 5], 
                        color: '#f1f5f9' 
                    }
                },
                x: { 
                    grid: { display: false } 
                }
            }
        }
    });
});