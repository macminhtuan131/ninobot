"""Strict same-session endpoint identity; no ROS imports or publishers."""
ALLOWED_HARDWARE_NAMES={'stm32h7_node','_CREATED_BY_BARE_DDS_APP_'}

def gid(endpoint):
    return bytes(endpoint.endpoint_gid).hex()

def verify(node,pins,matched_count):
    errors=[];observed={}
    for topic,pin in pins['endpoints'].items():
        method=node.get_publishers_info_by_topic if pin['direction']=='publishers' else node.get_subscriptions_info_by_topic
        endpoints=method(topic)
        observed[topic]=[{'node':e.node_name,'gid':gid(e),'type':e.topic_type} for e in endpoints]
        matches=[e for e in endpoints if gid(e)==pin['gid'] and e.topic_type==pin['type'] and e.node_name in ALLOWED_HARDWARE_NAMES]
        if len(matches)!=1:errors.append('Pinned STM32 endpoint absent/mismatched on '+topic)
        if pin['direction']=='publishers' and len(endpoints)!=1:errors.append('Unexpected telemetry publisher count on '+topic)
    source_recorders=[e for e in node.get_subscriptions_info_by_topic('/cmd_vel_teleop') if e.node_name=='nino_real_data_recorder']
    enable_recorders=[e for e in node.get_subscriptions_info_by_topic('/motor_enable') if e.node_name=='nino_real_data_recorder']
    if len(source_recorders)!=1 or len(enable_recorders)!=1:
        errors.append('Recorder source/enable endpoint not discovered')
    elif gid(source_recorders[0])[:24]!=gid(enable_recorders[0])[:24]:
        errors.append('Recorder source/enable participant mismatch')
    if matched_count<2:errors.append('Enable publisher has fewer than two matched DDS subscriptions')
    return {'errors':errors,'hardware_endpoints':observed,'enable_matched_subscriptions':matched_count,'recorder_source_gids':[gid(e) for e in source_recorders],'recorder_enable_gids':[gid(e) for e in enable_recorders]}
