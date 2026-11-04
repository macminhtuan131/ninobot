"""Frozen window metrics from original receipt-timed CSV; no resampling."""
import math,statistics
JOINTS=('left_wheel','right_wheel')
GAP_S=.100

def window(samples,a,b,gap_s=GAP_S):
    values=[s for s in samples if a<=s[0]<b]
    reasons=[]
    if len(values)<2:return values,['fewer_than_two_samples']
    if values[0][0]-a>gap_s or b-values[-1][0]>gap_s:reasons.append('boundary_support_over_limit')
    if any(y[0]-x[0]>gap_s for x,y in zip(values,values[1:])):reasons.append('receipt_gap_over_limit')
    if any(not math.isfinite(s[1]) for s in values):reasons.append('nonfinite_values')
    stamps=[s[2] for s in values if len(s)>2]
    if stamps:
        if any(y<=x for x,y in zip(stamps,stamps[1:])):reasons.append('source_header_nonincreasing')
        if any(y-x>100000000 for x,y in zip(stamps,stamps[1:])):reasons.append('source_gap_over_100ms')
    return values,reasons

def evaluate(rows):
    command=[(float(r['bag_time_relative_source_s']),float(r['velocity_value'])) for r in rows if r['topic']=='/cmd_vel']
    primary_cmd,command_reasons=window(command,1.25,1.75,gap_s=.2)
    if any(abs(s[1]-.05)>1e-6 for s in primary_cmd):command_reasons.append('primary_reference_not_005')
    baseline_cmd,baseline_command_reasons=window(command,-2.,0.,gap_s=.2)
    if any(s[1]!=0. for s in baseline_cmd):baseline_command_reasons.append('baseline_reference_not_zero')
    report={'windows_s':{'baseline':[-2.,0.],'primary':[1.25,1.75]},'command_reasons':command_reasons+baseline_command_reasons,'wheels':{},'scope':'Arithmetic means of original samples; nominal final reference, not executed wheel target or actuator latency.'}
    for joint in JOINTS:
        samples=[(float(r['bag_time_relative_source_s']),float(r['velocity_value']),int(r['source_header_ns'])) for r in rows if r['topic']=='/motor_fb' and r['joint']==joint]
        base,br=window(samples,-2.,0.);primary,pr=window(samples,1.25,1.75)
        valid=not (br or pr or report['command_reasons'])
        report['wheels'][joint]={'valid':valid,'baseline_count':len(base),'primary_count':len(primary),'reasons':br+pr,
            'delta_mean_velocity_rad_s':statistics.mean(s[1] for s in primary)-statistics.mean(s[1] for s in base) if valid else None,
            'baseline_mean_velocity_rad_s':statistics.mean(s[1] for s in base) if base and all(math.isfinite(s[1]) for s in base) else None,
            'primary_mean_velocity_rad_s':statistics.mean(s[1] for s in primary) if primary and all(math.isfinite(s[1]) for s in primary) else None}
    report['primary_valid']=all(w['valid'] for w in report['wheels'].values())
    report['left_minus_right_delta_mean_rad_s']=report['wheels'][JOINTS[0]]['delta_mean_velocity_rad_s']-report['wheels'][JOINTS[1]]['delta_mean_velocity_rad_s'] if report['primary_valid'] else None
    return report
