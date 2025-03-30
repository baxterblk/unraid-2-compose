from flask import Flask, render_template, request, jsonify
import xml.etree.ElementTree as ET
import yaml
import re
import json

app = Flask(__name__, static_url_path='/static', static_folder='static')

def represent_str_as_yaml_str(dumper, data):
    if '\n' in data or ':' in data or '{' in data or '}' in data or '[' in data or ']' in data:
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)

def parse_xml_data(xml_data):
    try:
        # Parse XML from string
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        raise Exception(f"Invalid XML data: {e}")
    
    container_name = root.find('Name')
    if container_name is None:
        raise Exception("Container name not found in XML")
    container_name = container_name.text
    
    image = root.find('Repository')
    if image is None:
        raise Exception("Repository (image) not found in XML")
    image = image.text
    
    # Check if privileged mode is enabled
    privileged_elem = root.find('Privileged')
    privileged = privileged_elem is not None and privileged_elem.text and privileged_elem.text.lower() == 'true'
    
    # Get network information
    network_elem = root.find('Network')
    network_mode = None
    networks = []
    
    if network_elem is not None and network_elem.text:
        if network_elem.text.lower() in ['host', 'bridge', 'none']:
            network_mode = network_elem.text.lower()
        elif network_elem.text:
            networks.append(network_elem.text)
    
    # Get restart policy - unRAID doesn't explicitly define this, default to 'unless-stopped'
    restart = 'unless-stopped'
    
    # Get CPU settings
    extra_params_elem = root.find('ExtraParams')
    extra_params = extra_params_elem.text if extra_params_elem is not None and extra_params_elem.text else ""
    cpuset_elem = root.find('CPUset')
    cpuset = cpuset_elem.text if cpuset_elem is not None and cpuset_elem.text else None
    
    # Parse CPU limits from extra_params
    cpu_limit = None
    cpu_shares = None
    memory_limit = None
    
    if extra_params:
        # Extract CPU limits
        cpus_match = re.search(r'--cpus=([0-9.]+)', extra_params)
        if cpus_match:
            cpu_limit = cpus_match.group(1)
        
        # Extract CPU shares
        cpu_shares_match = re.search(r'--cpu-shares=([0-9]+)', extra_params)
        if cpu_shares_match:
            cpu_shares = cpu_shares_match.group(1)
        
        # Extract memory limits
        memory_match = re.search(r'--memory=([0-9]+[kmg]?)', extra_params, re.IGNORECASE)
        if memory_match:
            memory_limit = memory_match.group(1)
    
    # Get environment variables, volumes, and ports
    environment = {}
    volumes = []
    ports = []
    
    for config in root.findall('Config'):
        config_type = config.get('Type')
        if config_type is None:
            continue
            
        config_target = config.get('Target')
        if config_target is None:
            continue
            
        config_value = config.text
        
        if config_type == 'Variable':
            if config_value is not None:
                environment[config_target] = config_value
        elif config_type == 'Path':
            if config_value is not None:
                host_path = config_value
                container_path = config_target
                # Check if it's read-only
                mode = config.get('Mode', '')
                if mode and 'ro' in mode:
                    volumes.append(f"{host_path}:{container_path}:ro")
                else:
                    volumes.append(f"{host_path}:{container_path}")
        elif config_type == 'Port':
            if config_value is not None:
                host_port = config_value
                container_port = config_target
                # Get the protocol (tcp/udp)
                mode = config.get('Mode', '')
                protocol = ''
                if 'tcp' in mode:
                    protocol = 'tcp'
                elif 'udp' in mode:
                    protocol = 'udp'
                else:
                    protocol = 'tcp'  # Default to TCP
                
                ports.append(f"{host_port}:{container_port}/{protocol}")
    
    # Create the service definition for docker-compose
    service = {
        'image': image,
        'container_name': container_name,
        'restart': restart
    }
    
    if environment:
        service['environment'] = environment
    
    if volumes:
        service['volumes'] = volumes
    
    if ports:
        service['ports'] = ports
    
    if privileged:
        service['privileged'] = True
    
    if network_mode:
        service['network_mode'] = network_mode
    elif networks:
        service['networks'] = networks
    
    # Add resource constraints
    if cpu_limit or memory_limit or cpuset:
        if not cpu_limit and not memory_limit and cpuset:
            # Only cpuset
            service['cpuset'] = cpuset
        else:
            # CPU or memory limits - use deploy resources
            deploy = {}
            resources = {}
            
            if cpu_limit:
                limits = resources.get('limits', {})
                limits['cpus'] = cpu_limit
                resources['limits'] = limits
            
            if memory_limit:
                limits = resources.get('limits', {})
                limits['memory'] = memory_limit
                resources['limits'] = limits
                
            if cpuset:
                service['cpuset'] = cpuset
                
            if resources:
                deploy['resources'] = resources
                service['deploy'] = deploy
    
    if cpu_shares:
        # For CPU shares, use the old-style cpu_shares parameter
        service['cpu_shares'] = int(cpu_shares)
    
    # Get WebUI for documentation purposes
    webui_elem = root.find('WebUI')
    if webui_elem is not None and webui_elem.text:
        webui = webui_elem.text
        # Add as a comment/label
        service['labels'] = service.get('labels', {})
        service['labels']['unraid.webui'] = webui
    
    # Get Support URL for documentation
    support_elem = root.find('Support')
    if support_elem is not None and support_elem.text:
        service['labels'] = service.get('labels', {})
        service['labels']['unraid.support'] = support_elem.text
    
    # Get Project URL for documentation
    project_elem = root.find('Project')
    if project_elem is not None and project_elem.text:
        service['labels'] = service.get('labels', {})
        service['labels']['unraid.project'] = project_elem.text
    
    return container_name, service, networks

def convert_xml_to_compose(xml_data):
    compose = {
        'services': {}
    }
    
    all_networks = set()
    
    try:
        container_name, service, networks = parse_xml_data(xml_data)
        compose['services'][container_name] = service
        
        # Collect networks
        for network in networks:
            all_networks.add(network)
    except Exception as e:
        return None, str(e)
    
    # Add networks section if needed
    if all_networks:
        compose['networks'] = {}
        for network in all_networks:
            compose['networks'][network] = {'external': True}
    
    # Set up YAML representation
    yaml.add_representer(str, represent_str_as_yaml_str)
    
    # Convert to YAML
    yaml_str = yaml.dump(compose, default_flow_style=False, sort_keys=False)
    
    return yaml_str, None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    xml_data = request.form.get('xml_data', '')
    if not xml_data:
        return jsonify({'error': 'No XML data provided'})
    
    yaml_data, error = convert_xml_to_compose(xml_data)
    if error:
        return jsonify({'error': error})
    
    return jsonify({'yaml': yaml_data})

@app.route('/add-autokuma-labels', methods=['POST'])
def add_autokuma_labels():
    try:
        # Parse request data
        compose_yaml = request.form.get('compose_yaml', '')
        monitors_json = request.form.get('monitors', '[]')
        service_name = request.form.get('service_name', '')
        
        if not compose_yaml:
            return jsonify({'error': 'No docker-compose.yml data provided'})
        
        monitors = json.loads(monitors_json)
        if len(monitors) == 0:
            return jsonify({'error': 'No monitors configured'})
        
        # Parse YAML to Python object
        compose = yaml.safe_load(compose_yaml)
        
        if not compose or 'services' not in compose or len(compose['services']) == 0:
            return jsonify({'error': 'Invalid docker-compose.yml format or no services found'})
        
        # Find the target service
        if not service_name:
            # Use the first service if not specified
            service_name = list(compose['services'].keys())[0]
        elif service_name not in compose['services']:
            return jsonify({'error': f'Service "{service_name}" not found in docker-compose.yml'})
        
        service = compose['services'][service_name]
        
        # Initialize labels if needed
        if 'labels' not in service:
            service['labels'] = []
        elif isinstance(service['labels'], dict):
            # Convert dict to list
            service['labels'] = [f"{k}={v}" for k, v in service['labels'].items()]
        
        # Add AutoKuma labels for each monitor
        for monitor in monitors:
            if monitor['type'] == 'group':
                # Group labels
                service['labels'].append(f"kuma.group.name={monitor['name']}")
                service['labels'].append(f"kuma.group.id={monitor['id']}")
                if monitor.get('description'):
                    service['labels'].append(f"kuma.group.description={monitor['description']}")
            
            elif monitor['type'] == 'docker':
                # Docker monitor labels
                service['labels'].append(f"kuma.monitor.type=docker")
                service['labels'].append(f"kuma.monitor.id={monitor['id']}")
                service['labels'].append(f"kuma.monitor.name={monitor['name']}")
                if monitor.get('description'):
                    service['labels'].append(f"kuma.monitor.description={monitor['description']}")
                if monitor.get('parent'):
                    service['labels'].append(f"kuma.monitor.parent={monitor['parent']}")
                service['labels'].append(f"kuma.monitor.docker.host={monitor['host']}")
                service['labels'].append(f"kuma.monitor.docker.container={monitor['container']}")
                service['labels'].append(f"kuma.monitor.interval={monitor['interval']}")
                service['labels'].append(f"kuma.monitor.retry.interval={monitor['retry']}")
                service['labels'].append(f"kuma.monitor.max.retries={monitor['maxretry']}")
            
            elif monitor['type'] == 'http':
                # HTTP monitor labels
                service['labels'].append(f"kuma.monitor.type=http")
                service['labels'].append(f"kuma.monitor.id={monitor['id']}")
                service['labels'].append(f"kuma.monitor.name={monitor['name']}")
                if monitor.get('description'):
                    service['labels'].append(f"kuma.monitor.description={monitor['description']}")
                if monitor.get('parent'):
                    service['labels'].append(f"kuma.monitor.parent={monitor['parent']}")
                service['labels'].append(f"kuma.monitor.http.url={monitor['url']}")
                service['labels'].append(f"kuma.monitor.interval={monitor['interval']}")
                service['labels'].append(f"kuma.monitor.retry.interval={monitor['retry']}")
                service['labels'].append(f"kuma.monitor.max.retries={monitor['maxretry']}")
                service['labels'].append(f"kuma.monitor.http.timeout={monitor['timeout']}")
                if monitor.get('keyword'):
                    service['labels'].append(f"kuma.monitor.http.keyword={monitor['keyword']}")
            
            elif monitor['type'] == 'port':
                # Port monitor labels
                service['labels'].append(f"kuma.monitor.type=port")
                service['labels'].append(f"kuma.monitor.id={monitor['id']}")
                service['labels'].append(f"kuma.monitor.name={monitor['name']}")
                if monitor.get('description'):
                    service['labels'].append(f"kuma.monitor.description={monitor['description']}")
                if monitor.get('parent'):
                    service['labels'].append(f"kuma.monitor.parent={monitor['parent']}")
                service['labels'].append(f"kuma.monitor.port.hostname={monitor['hostname']}")
                service['labels'].append(f"kuma.monitor.port.port={monitor['port']}")
                service['labels'].append(f"kuma.monitor.interval={monitor['interval']}")
                service['labels'].append(f"kuma.monitor.retry.interval={monitor['retry']}")
                service['labels'].append(f"kuma.monitor.max.retries={monitor['maxretry']}")
        
        # Convert back to YAML
        yaml_str = yaml.dump(compose, default_flow_style=False, sort_keys=False)
        
        return jsonify({'yaml': yaml_str})
    
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
