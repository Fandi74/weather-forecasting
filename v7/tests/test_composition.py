import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from composition import compose_forecasts, point_forecasts

def inputs():
    hourly = []
    for station in ['X50','X51','X66','X67']:
        for h in range(1,25):
            hourly.append({'station':station,'issue':0,'time':h*3600,'selected_t':20+h/10,
                'selected_h':80-h/10,'selected_rain':.1,'selected_rain_probability':.2,
                'humidity_method':'equal_three' if station=='X66' else 'retained_v2'})
    rain = [{'station':s,'issue':0,'horizon':h,'end':h*3600,'selected_amount':h*.2,
        'selected_probability':.3,'selected_amount_method':'test_v6_amount',
        'selected_probability_method':'test_v6_probability'} for s in ['X50','X66'] for h in [1,6,12,24]]
    return hourly,rain

class CompositionTests(unittest.TestCase):
    def test_point_components_are_preserved_without_mutation(self):
        hourly,rain=inputs();before=copy.deepcopy((hourly,rain))
        rows=compose_forecasts(hourly,rain)
        for row in rows:
            self.assertEqual(row['temperature_c'],20+row['horizon']/10)
            self.assertEqual(row['humidity_pct'],80-row['horizon']/10)
        self.assertEqual((hourly,rain),before)
        self.assertEqual(len(point_forecasts(hourly)),96)

    def test_direct_rain_windows_are_not_accumulated_again(self):
        rows=compose_forecasts(*inputs())
        x=[r for r in rows if r['station']=='X66' and r['horizon']==24][0]
        self.assertAlmostEqual(x['rainfall_mm'],4.8)
        self.assertEqual(x['rain_probability'],.3)

    def test_fallback_has_no_invented_joint_probability(self):
        rows=compose_forecasts(*inputs())
        for row in rows:
            if row['station'] in ['X51','X67']:
                self.assertAlmostEqual(row['rainfall_mm'],row['horizon']*.1)
                self.assertEqual(row['rain_probability'],.2 if row['horizon']==1 else None)

    def test_mismatched_issue_rejected(self):
        hourly,rain=inputs();rain[0]['issue']=1
        with self.assertRaises(ValueError):compose_forecasts(hourly,rain)

    def test_mismatched_window_end_rejected(self):
        hourly,rain=inputs();rain[0]['end']+=3600
        with self.assertRaises(ValueError):compose_forecasts(hourly,rain)

    def test_missing_rain_window_rejected(self):
        hourly,rain=inputs();rain.pop()
        with self.assertRaises(ValueError):compose_forecasts(hourly,rain)

    def test_duplicate_rain_window_rejected(self):
        hourly,rain=inputs();rain.append(dict(rain[0]))
        with self.assertRaises(ValueError):compose_forecasts(hourly,rain)

    def test_hourly_gap_rejected(self):
        hourly,rain=inputs();hourly.pop(2)
        with self.assertRaises(ValueError):compose_forecasts(hourly,rain)

    def test_duplicate_hourly_point_rejected(self):
        hourly,rain=inputs();hourly.append(dict(hourly[0]))
        with self.assertRaises(ValueError):compose_forecasts(hourly,rain)

    def test_invalid_rain_probability_rejected(self):
        hourly,rain=inputs();rain[0]['selected_probability']=1.1
        with self.assertRaises(ValueError):compose_forecasts(hourly,rain)

    def test_negative_rain_rejected(self):
        hourly,rain=inputs();rain[0]['selected_amount']=-1
        with self.assertRaises(ValueError):compose_forecasts(hourly,rain)

if __name__=='__main__':
    unittest.main()
