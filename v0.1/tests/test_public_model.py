import copy
import math
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from metrics import continuous,rain_event
from engine import compose,load,predict_points,predict_rain_windows
from run import verify_replay
from verify_package import privacy_structure

class PublicModelTests(unittest.TestCase):
    def test_temperature_percentage_has_explicit_tolerance(self):
        self.assertAlmostEqual(continuous([10,10,10],[10,10.5,11.5],1)['within_tolerance_pct'],200/3)
    def test_humidity_tolerance_uses_percentage_points(self):
        score=continuous([50,60],[55,66],5)
        self.assertEqual(score['within_tolerance_count'],1)
        self.assertEqual(score['within_tolerance_pct'],50)
    def test_imbalanced_rain_accuracy_is_not_balanced_accuracy(self):
        score=rain_event([0]*9+[.28],[0]*10)
        self.assertEqual(score['accuracy_pct'],90)
        self.assertEqual(score['balanced_accuracy_pct'],50)
        self.assertEqual(score['recall_pct'],0)
    def test_no_wet_cases_has_no_balanced_score(self):
        self.assertIsNone(rain_event([0,0],[0,0])['balanced_accuracy_pct'])
    def test_invalid_probability_rejected(self):
        with self.assertRaises(ValueError):rain_event([0],[1.1])
    def test_unmatched_continuous_samples_rejected(self):
        with self.assertRaises(ValueError):continuous([1,2],[1],1)
    def test_future_rain_context_rejected(self):
        rows=load('data/rain_inputs.json')
        rows[0]['max_context_available_offset_hours']=.1
        with self.assertRaises(ValueError):predict_rain_windows(rows)
    def test_missing_point_coverage_rejected(self):
        with self.assertRaises(ValueError):compose([{'site':'Site C','lead_hours':1,'temperature_c':20,'humidity_pct':50,'baseline_rain_mm':.1,'baseline_rain_probability':.2}],[])
    def test_missing_direct_rain_windows_rejected(self):
        points=[{'site':'Site A','lead_hours':h,'temperature_c':20,'humidity_pct':50,
            'baseline_rain_mm':.1,'baseline_rain_probability':.2} for h in range(1,25)]
        with self.assertRaises(ValueError):compose(points,[])
    def test_fallback_does_not_add_probabilities(self):
        points=[{'site':'Site C','lead_hours':h,'temperature_c':20,'humidity_pct':50,
            'baseline_rain_mm':.1,'baseline_rain_probability':.2} for h in range(1,25)]
        result=compose(points,[])
        self.assertAlmostEqual(result[-1]['rainfall_mm'],2.4)
        self.assertIsNone(result[-1]['rain_probability'])
    def test_structural_privacy_scan(self):
        self.assertEqual(privacy_structure(),[])
    def test_cleaned_native_model_replay(self):
        result=verify_replay()
        self.assertEqual(result['point_forecasts_reproduced'],672)
        self.assertEqual(result['rain_windows_reproduced'],8)
        self.assertEqual(result['combined_windows_reproduced'],16)

if __name__=='__main__':unittest.main()
