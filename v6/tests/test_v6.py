from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from common import TRAIN_END,VALIDATION_END
from data import normalize,rain_hours,soil_change,window_label
from features import History,names
from samples import partition


def station_data(missing=(),rain=.28,wrong_gap_rid=False):
    rows=[]
    for i in range(7):
        if i in missing:continue
        r=normalize({'timestamp_ms':str((i*600+8)*1000),'rf':str(rain if i else 0),'rfc':str(i if rain else 0),
            'srm':str(10000-i*10),'sm':'20','rid':str(i),'error':'E3 E12'})
        rows.append(r)
    if wrong_gap_rid:
        rows[3]['rid']=rows[2]['rid']+1
    hours,intervals,qc=rain_hours(rows)
    return {'records':rows,'times':[r['time'] for r in rows],'hours':hours,'intervals':intervals}


class V6Tests(unittest.TestCase):
    def test_e11_excludes_soil_but_not_rain(self):
        r=normalize({'timestamp_ms':'8000','rf':'.28','rfc':'1','srm':'1000','sm':'90','error':'E3 E8 E11 E12'})
        self.assertIsNone(r['srm']);self.assertTrue(r['rain_ok'])

    def test_rf_is_mm_not_multiplied_by_tip_twice(self):
        d=station_data();label=window_label(d,0,1)
        self.assertAlmostEqual(label['amount'],1.68)

    def test_counter_recovers_whole_window_only_with_record_continuity(self):
        d=station_data(missing=(3,4))
        label=window_label(d,0,1)
        self.assertEqual(label['source'],'counter_endpoints_packet_continuity')
        self.assertAlmostEqual(label['amount'],1.68)
        broken=station_data(missing=(3,4),wrong_gap_rid=True)
        self.assertIsNone(window_label(broken,0,1))

    def test_counter_recovery_requires_both_boundaries(self):
        self.assertIsNone(window_label(station_data(missing=(0,3,4)),0,1))

    def test_reset_is_not_a_counter_total(self):
        d=station_data(missing=(3,4));d['records'][-1]['rfc']=0
        self.assertIsNone(window_label(d,0,1))

    def test_no_neighbor_label_copy(self):
        own=station_data(rain=0);neighbor=station_data()
        self.assertEqual(window_label(own,0,1)['amount'],0)
        self.assertGreater(window_label(neighbor,0,1)['amount'],0)

    def test_future_observations_cannot_change_history(self):
        d=station_data();first=History({'X50':d,'X66':d}).get('X50',3600)
        later=station_data();later['records'].append(normalize({'timestamp_ms':'10808000','rf':'9.52','rfc':'99','srm':'500','sm':'100','rid':'18','error':''}));later['times'].append(10808)
        after=History({'X50':later,'X66':later}).get('X50',3600)
        self.assertEqual(first,after)

    def test_soil_history_expires_and_future_soil_is_never_used(self):
        d=station_data();history=History({'X50':d,'X66':d})
        a=history.get('X50',7200)
        self.assertEqual(a['srm_latest'],d['records'][-2]['srm'])
        self.assertIsNone(history.get('X50',12*3600)['srm_latest'])
        self.assertTrue(all(r['max_measurement_receipt_used'] is None or r['max_measurement_receipt_used']<=r['issue'] for r in history.audit))

    def test_soil_change_cannot_bridge_gaps(self):
        self.assertIsNone(soil_change(station_data(missing=(3,4)),3608,60))

    def test_split_purges_future_window_receipts(self):
        self.assertEqual(partition(TRAIN_END-3600,TRAIN_END+1),'purged_boundary')
        self.assertEqual(partition(TRAIN_END,TRAIN_END+7200),'validation')
        self.assertEqual(partition(VALIDATION_END-3600,VALIDATION_END+1),'purged_boundary')

    def test_ablations_isolate_soil_and_neighbor(self):
        self.assertNotIn('own_srm_latest',names('local_rain'))
        self.assertIn('own_srm_latest',names('local_rain_soil'))
        self.assertNotIn('neighbor_rain_latest_mm',names('local_rain_soil'))
        self.assertIn('neighbor_rain_latest_mm',names('network_rain'))
        self.assertIn('neighbor_srm_latest',names('network_rain_soil'))


if __name__=='__main__':unittest.main()
