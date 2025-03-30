# Fix updateMonitorList function
/case 'http':/{
  N
  N
  N
  N
  N
  N
  N
  N
  s/details = `<strong>HTTP Monitor:<\/strong>/details = `<strong>HTTP Monitor:<\/strong>/
  s/details \+=.*$/details += `<br><strong>URL:<\/strong> ${monitor.url}`;
                        if (monitor.parent) {
                            details += `<br><strong>Parent Group:<\/strong> ${monitor.parent}`;
                        }
                        break;
                        
                    case 'port':
                        details = `<strong>Port Monitor:<\/strong> ${monitor.name}`;
                        details += `<br><strong>Host:Port:<\/strong> ${monitor.hostname}:${monitor.port}`;
                        if (monitor.parent) {
                            details += `<br><strong>Parent Group:<\/strong> ${monitor.parent}`;
                        }
                        break;
                }/
}

# Add closing bracket for updateMonitorList and add addAutoKumaLabels function
/html \+= `$/,/\];/{
  s/\];$/\];
            
            listElement.innerHTML = html;
        }
        
        function addAutoKumaLabels() {
            const composeInput = document.getElementById('compose-input').value.trim();
            const errorElement = document.getElementById('autokuma-error-message');
            const copyBtn = document.getElementById('autokuma-copy-btn');
            const downloadBtn = document.getElementById('autokuma-download-btn');
            
            if (!composeInput) {
                errorElement.textContent = "Please paste docker-compose.yml content first";
                return;
            }
            
            if (monitors.length === 0) {
                errorElement.textContent = "Please add at least one monitor configuration";
                return;
            }
            
            errorElement.textContent = '';
            
            fetch('\/add-autokuma-labels', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application\/x-www-form-urlencoded',
                },
                body: new URLSearchParams({
                    'compose_yaml': composeInput,
                    'monitors': JSON.stringify(monitors),
                    'service_name': document.getElementById('service-name').value.trim()
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    errorElement.textContent = data.error;
                    document.getElementById('autokuma-output').value = '';
                    copyBtn.style.display = 'none';
                    downloadBtn.style.display = 'none';
                } else {
                    document.getElementById('autokuma-output').value = data.yaml;
                    copyBtn.style.display = 'block';
                    downloadBtn.style.display = 'block';
                }
            })
            .catch(error => {
                errorElement.textContent = "An error occurred while adding labels: " + error;
                copyBtn.style.display = 'none';
                downloadBtn.style.display = 'none';
            });
        }
    <\/script>
<\/body>
<\/html>/
}
