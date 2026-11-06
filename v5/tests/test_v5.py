import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import FREEZE, no_overwrite
from data import eligible, prepare_sht, sht_value
from ensemble import eligible_calibration, fit, predict
from features import History
from run import check_passthrough, preserve_components


class V5Tests(unittest.TestCase):
    def test_sht_labels_never_use_h_and_bme_fault_does_not_remove_sht(self):
        self.assertEqual(sht_value({'hsht':'72','h':'100','error':'E2 E3 E8 E12'}),72)
        self.assertIsNone(sht_value({'h':'100','error':''}))
        self.assertIsNone(sht_value({'hsht':'72','error':'E99'}))

    def test_training_excludes_late_arrivals_and_cutoff_labels(self):
        row={'station':'X66','time':FREEZE-3600,'issue':FREEZE-168*3600,'forecast_t':20,'forecast_h':80,'forecast_rain':0}
        obs={row['time']:{'time':row['time'],'value':75,'observed_at':row['time']+8,'available_at':FREEZE+8}}
        self.assertEqual(eligible([row],obs,FREEZE),[])

    def test_calibration_purges_unreceived_boundary(self):
        rows=[{'issue':0,'time':10,'observed_at':18,'available_at':20}, {'issue':0,'time':10,'observed_at':11,'available_at':19}]
        self.assertEqual(eligible_calibration(rows,20),[rows[1]])

    def test_future_observations_cannot_change_features(self):
        observations={0:{'time':0,'value':70,'observed_at':0,'available_at':3600}}
        first=History(observations,[]).get(7200)
        extended={**observations,10800:{'time':10800,'value':100,'observed_at':10800,'available_at':14400}}
        self.assertEqual(first,History(extended,[]).get(7200))

    def test_expired_humidity_remains_missing(self):
        history=History({0:{'time':0,'value':70,'observed_at':0,'available_at':3600}},[])
        result=history.get(9*3600)
        self.assertIsNone(result['hsht_latest'])
        self.assertIsNone(result['hsht_24h_mean'])
        self.assertEqual(result['hsht_age_hours'],9)

    def test_convex_weights_and_bounds(self):
        rows=[{'v2_h':a,'catboost_hsht_h':a-10,'lightgbm_hsht_h':a+10,'observed':a-5} for a in [50,60,70,80]]
        model=fit(rows,'convex')
        self.assertAlmostEqual(sum(model['weights']),1)
        self.assertTrue(all(0<=w<=1 for w in model['weights']))
        self.assertTrue(all(abs(a-b)<1e-8 for a,b in zip(predict(model,rows),[r['observed'] for r in rows])))
        shifted={**model,'bias_pp':100}
        self.assertTrue(all(v==100 for v in predict(shifted,rows)))

    def test_temperature_rain_and_probability_passthrough(self):
        original=[{'station':s,'time':i*3600,'issue':0,'day':1,'v2_t':21.125,'v2_h':90,'v2_rain':.028,'rain_probability':.25} for s in ['X50','X51','X66','X67'] for i in range(1,169)]
        previous={m:{(r['station'],r['time']):{'selected_h':85} for r in original} for m in ['V3','V4']}
        humidity={i*3600:{'selected_h':80,'catboost_hsht_h':79,'lightgbm_hsht_h':81} for i in range(1,169)}
        result=preserve_components(original,previous,humidity,{'family':'convex'})
        self.assertEqual(check_passthrough(result,original),672)
        self.assertTrue(all(r['selected_h']==80 for r in result if r['station']=='X66'))
        self.assertTrue(all(r['selected_h']==90 for r in result if r['station']!='X66'))
        result[0]['selected_t']+=.001
        with self.assertRaises(ValueError): check_passthrough(result,original)

    def test_sealed_output_cannot_be_overwritten(self):
        temporary_root=Path(__file__).resolve().parents[1]/'.test_temp'
        temporary_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary_root) as folder:
            self.assertTrue(Path(folder).resolve().is_relative_to(temporary_root.resolve()))
            Path(folder,'candidate_lock.json').write_text('{}')
            with self.assertRaises(ValueError): no_overwrite(folder)

    def test_worker_cannot_train_temperature_or_rain(self):
        from worker import run
        for target in ['temperature','rain']:
            with patch('worker.read_json',return_value={'target':target}):
                with self.assertRaises(ValueError): run('unused')

    def test_post_cutoff_source_cannot_enter_training(self):
        with self.assertRaises(ValueError):
            prepare_sht([{'timestamp_ms':str(int((FREEZE+8)*1000)),'hsht':'80','error':''}])


if __name__=='__main__':
    unittest.main()
