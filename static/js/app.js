document.addEventListener('DOMContentLoaded', function() {
    let statusUpdateInterval;

    initPasswordToggle();
    initTooltips();
    startStatusPolling();

    function updateNavigationStatus() {
        fetch('/api/monitoring_status')
            .then(response => response.json())
            .then(data => {
                const statusElement = document.getElementById('monitoring-status');
                if (statusElement) {
                    if (data.running) {
                        statusElement.innerHTML = '<i class="bi bi-circle-fill text-success"></i> 运行中';
                        statusElement.className = 'badge bg-success';
                    } else {
                        statusElement.innerHTML = '<i class="bi bi-circle-fill text-danger"></i> 已停止';
                        statusElement.className = 'badge bg-danger';
                    }
                }

                const lastUpdateElement = document.querySelector('.navbar-text small');
                if (lastUpdateElement && data.last_update) {
                    lastUpdateElement.textContent = `最后更新：${formatTime(data.last_update)}`;
                }
            })
            .catch(error => {
                console.error('获取监控状态失败:', error);
            });
    }

    function startStatusPolling() {
        if (statusUpdateInterval) {
            clearInterval(statusUpdateInterval);
        }
        updateNavigationStatus();
        statusUpdateInterval = setInterval(updateNavigationStatus, 10000);
    }

    function stopStatusPolling() {
        if (statusUpdateInterval) {
            clearInterval(statusUpdateInterval);
        }
    }

    function initPasswordToggle() {
        const passwordInputs = document.querySelectorAll('input[type="password"]');
        passwordInputs.forEach(input => {
            const existingToggle = input.parentNode.querySelector('.password-toggle');
            if (existingToggle) return;

            const toggleBtn = document.createElement('button');
            toggleBtn.type = 'button';
            toggleBtn.className = 'btn btn-outline-secondary password-toggle';
            toggleBtn.innerHTML = '<i class="bi bi-eye"></i>';
            toggleBtn.style.cssText = 'position: absolute; right: 5px; top: 50%; transform: translateY(-50%); z-index: 10; border: none; background: transparent;';

            input.parentNode.style.position = 'relative';
            input.style.paddingRight = '45px';

            toggleBtn.addEventListener('click', function() {
                if (input.type === 'password') {
                    input.type = 'text';
                    this.innerHTML = '<i class="bi bi-eye-slash"></i>';
                } else {
                    input.type = 'password';
                    this.innerHTML = '<i class="bi bi-eye"></i>';
                }
            });

            input.parentNode.appendChild(toggleBtn);
        });
    }

    function initTooltips() {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function(tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }

    window.addEventListener('beforeunload', function() {
        stopStatusPolling();
    });

    window.TwitterAI = {
        updateNavigationStatus,
        startStatusPolling,
        stopStatusPolling,
        showMessage
    };
});

function showMessage(message, type = 'success') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="关闭"></button>
    `;

    document.body.appendChild(alertDiv);

    setTimeout(() => {
        if (alertDiv && alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 3000);
}

function formatTime(timeString) {
    if (!timeString) return '';
    const date = new Date(timeString);
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
}

function truncateText(text, maxLength = 100) {
    const value = String(text || '');
    if (value.length <= maxLength) {
        return value;
    }
    return value.substring(0, maxLength) + '...';
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

class API {
    static async request(url, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        };

        try {
            const response = await fetch(url, {...defaultOptions, ...options});
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.message || '请求失败');
            }

            return data;
        } catch (error) {
            console.error('API请求失败:', error);
            throw error;
        }
    }

    static async saveConfig(config) {
        return this.request('/api/save_config', {
            method: 'POST',
            body: JSON.stringify(config)
        });
    }

    static async startMonitoring() {
        return this.request('/api/start_monitoring', {method: 'POST'});
    }

    static async stopMonitoring() {
        return this.request('/api/stop_monitoring', {method: 'POST'});
    }

    static async getMonitoringStatus() {
        return this.request('/api/monitoring_status');
    }

    static async getTweets(filters = {}) {
        const params = new URLSearchParams(filters);
        return this.request(`/api/tweets?${params}`);
    }
}

window.API = API;
window.formatTime = formatTime;
window.truncateText = truncateText;
window.debounce = debounce;
