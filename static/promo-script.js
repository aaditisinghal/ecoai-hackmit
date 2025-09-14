// EcoAI Promo Site JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // Initialize animations and interactions
    initializeAnimations();
    initializeChart();
    initializeCounters();
    initializeScrollEffects();
});

// Counter animation for statistics
function initializeCounters() {
    const counters = document.querySelectorAll('[data-target]');
    
    const animateCounter = (counter) => {
        const target = parseFloat(counter.getAttribute('data-target'));
        const increment = target / 100;
        let current = 0;
        
        const updateCounter = () => {
            if (current < target) {
                current += increment;
                if (current > target) current = target;
                
                if (target < 10) {
                    counter.textContent = current.toFixed(3);
                } else if (target < 100) {
                    counter.textContent = current.toFixed(1);
                } else {
                    counter.textContent = Math.floor(current).toLocaleString();
                }
                
                requestAnimationFrame(updateCounter);
            }
        };
        
        updateCounter();
    };
    
    // Intersection Observer for counters
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const counter = entry.target;
                animateCounter(counter);
                observer.unobserve(counter);
            }
        });
    });
    
    counters.forEach(counter => observer.observe(counter));
}

// Chart.js for savings visualization
function initializeChart() {
    const ctx = document.getElementById('savingsChart');
    if (!ctx) return;
    
    // Sample data - in real implementation, this would come from API
    const chartData = {
        labels: ['Jan 9', 'Jan 10', 'Jan 11', 'Jan 12', 'Jan 13', 'Jan 14', 'Jan 15'],
        datasets: [{
            label: 'Tokens Saved',
            data: [45, 52, 38, 67, 58, 72, 89],
            borderColor: '#34D399',
            backgroundColor: 'rgba(52, 211, 153, 0.1)',
            borderWidth: 3,
            fill: true,
            tension: 0.4
        }, {
            label: 'CO₂ Saved (g)',
            data: [0.045, 0.052, 0.038, 0.067, 0.058, 0.072, 0.089],
            borderColor: '#60A5FA',
            backgroundColor: 'rgba(96, 165, 250, 0.1)',
            borderWidth: 3,
            fill: true,
            tension: 0.4,
            yAxisID: 'y1'
        }]
    };
    
    const chart = new Chart(ctx, {
        type: 'line',
        data: chartData,
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: {
                        color: '#a1a1aa',
                        font: {
                            size: 12
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: {
                        color: '#27272a'
                    },
                    ticks: {
                        color: '#a1a1aa'
                    }
                },
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    grid: {
                        color: '#27272a'
                    },
                    ticks: {
                        color: '#a1a1aa'
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: {
                        drawOnChartArea: false,
                    },
                    ticks: {
                        color: '#a1a1aa'
                    }
                }
            }
        }
    });
    
    // Chart period controls
    document.querySelectorAll('.chart-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.chart-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            
            // In real implementation, fetch new data based on period
            const period = this.getAttribute('data-period');
            updateChartData(chart, period);
        });
    });
}

function updateChartData(chart, period) {
    // Simulate data fetching based on period
    let newData;
    switch(period) {
        case '7d':
            newData = {
                labels: ['Jan 9', 'Jan 10', 'Jan 11', 'Jan 12', 'Jan 13', 'Jan 14', 'Jan 15'],
                datasets: [{
                    data: [45, 52, 38, 67, 58, 72, 89]
                }, {
                    data: [0.045, 0.052, 0.038, 0.067, 0.058, 0.072, 0.089]
                }]
            };
            break;
        case '30d':
            newData = {
                labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4'],
                datasets: [{
                    data: [320, 380, 420, 450]
                }, {
                    data: [0.32, 0.38, 0.42, 0.45]
                }]
            };
            break;
        case '90d':
            newData = {
                labels: ['Month 1', 'Month 2', 'Month 3'],
                datasets: [{
                    data: [1200, 1450, 1680]
                }, {
                    data: [1.2, 1.45, 1.68]
                }]
            };
            break;
    }
    
    chart.data.labels = newData.labels;
    chart.data.datasets[0].data = newData.datasets[0].data;
    chart.data.datasets[1].data = newData.datasets[1].data;
    chart.update();
}

// Smooth scrolling for navigation
function scrollToSection(sectionId) {
    const element = document.getElementById(sectionId);
    if (element) {
        element.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
        });
    }
}

// Navigation functions
function openDocs() {
    // Redirect to the Flask portal login page
    window.location.href = '/login';
}

function openGitHub() {
    window.open('https://github.com/ecoai', '_blank');
}

function openContact() {
    // Redirect to the Flask portal login page
    window.location.href = '/login';
}

// Scroll effects and animations
function initializeScrollEffects() {
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };
    
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('animate');
            }
        });
    }, observerOptions);
    
    // Observe elements for animation
    document.querySelectorAll('.feature-card, .dashboard-card, .stat-card').forEach(el => {
        observer.observe(el);
    });
}

// Initialize all animations
function initializeAnimations() {
    // Add staggered animation delays
    document.querySelectorAll('.feature-card').forEach((card, index) => {
        card.style.animationDelay = `${index * 0.1}s`;
    });
    
    document.querySelectorAll('.stat-card').forEach((card, index) => {
        card.style.animationDelay = `${index * 0.2}s`;
    });
}

// Real-time data simulation (for demo purposes)
function simulateRealTimeData() {
    setInterval(() => {
        // Update receipt timestamps
        const timeElements = document.querySelectorAll('.time');
        timeElements.forEach(el => {
            const currentTime = new Date();
            const minutesAgo = Math.floor(Math.random() * 30) + 1;
            const newTime = new Date(currentTime.getTime() - minutesAgo * 60000);
            el.textContent = `${minutesAgo} min ago`;
        });
        
        // Occasionally add new receipt rows
        if (Math.random() < 0.1) { // 10% chance every 5 seconds
            addNewReceipt();
        }
    }, 5000);
}

function addNewReceipt() {
    const tableBody = document.querySelector('.table-body');
    if (!tableBody) return;
    
    const apps = [
        { icon: 'fas fa-code', name: 'Code Assistant' },
        { icon: 'fas fa-file-alt', name: 'Content Writer' },
        { icon: 'fas fa-search', name: 'Data Analyzer' },
        { icon: 'fas fa-comments', name: 'Chat Bot' }
    ];
    
    const app = apps[Math.floor(Math.random() * apps.length)];
    const tokenReduction = (Math.random() * 30 + 15).toFixed(1);
    const co2Reduction = (Math.random() * 35 + 20).toFixed(1);
    const quality = (Math.random() * 5 + 92).toFixed(1);
    
    const newRow = document.createElement('div');
    newRow.className = 'table-row';
    newRow.innerHTML = `
        <div class="table-cell">
            <div class="time-cell">
                <div class="time">Just now</div>
                <div class="date">${new Date().toLocaleDateString()}</div>
            </div>
        </div>
        <div class="table-cell">
            <div class="app-cell">
                <i class="${app.icon}"></i>
                <span>${app.name}</span>
            </div>
        </div>
        <div class="table-cell">
            <div class="percentage positive">-${tokenReduction}%</div>
        </div>
        <div class="table-cell">
            <div class="percentage positive">-${co2Reduction}%</div>
        </div>
        <div class="table-cell">
            <div class="quality-score">
                <div class="score">${quality}%</div>
                <div class="quality-bar">
                    <div class="quality-fill" style="width: ${quality}%"></div>
                </div>
            </div>
        </div>
        <div class="table-cell">
            <div class="status-badge success">
                <i class="fas fa-check"></i>
                Optimized
            </div>
        </div>
    `;
    
    // Add with animation
    newRow.style.opacity = '0';
    newRow.style.transform = 'translateY(20px)';
    tableBody.insertBefore(newRow, tableBody.firstChild);
    
    // Animate in
    setTimeout(() => {
        newRow.style.transition = 'all 0.5s ease';
        newRow.style.opacity = '1';
        newRow.style.transform = 'translateY(0)';
    }, 100);
    
    // Remove oldest row if we have too many
    const rows = tableBody.querySelectorAll('.table-row');
    if (rows.length > 5) {
        const oldestRow = rows[rows.length - 1];
        oldestRow.style.transition = 'all 0.5s ease';
        oldestRow.style.opacity = '0';
        oldestRow.style.transform = 'translateY(-20px)';
        setTimeout(() => oldestRow.remove(), 500);
    }
}

// Start real-time simulation
setTimeout(simulateRealTimeData, 2000);

// Export functions for global access
window.scrollToSection = scrollToSection;
window.openDocs = openDocs;
window.openGitHub = openGitHub;
window.openContact = openContact;
