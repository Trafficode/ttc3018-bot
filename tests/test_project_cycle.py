"""Real controller/probe/sender state machines; fake serial and fake CAM only."""
import copy
import time
import unittest
from unittest.mock import patch
from controller_fixture import Controller
from monitor.cam import write_json
from monitor.pcb_projects import PcbProjects
import test_pcb_projects as fixtures
from test_probes import Port

class ProjectCycleTests(unittest.TestCase):
    def setUp(self):
        fixture=fixtures.PcbProjectTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        self.fixture=fixture
        self.cnc=Controller();self.cnc.port=Port();self.cnc.info=['$6=1','$13=0']
        self.cnc._accept_status('<Idle|MPos:0,0,6|WCO:0,0,5|Pn:P>')
        self.cnc._accept_status('<Idle|MPos:0,0,6|WCO:0,0,5>')
        self.isolation=self.cnc.calibration.profiles.create({'source':'manual','name':'Fixture',
            'tip':.1,'angle':30,'feed':60,'plunge':5,'power':300,'depth':.08,
            'samples':[{'depth':.08,'width':1,'measured_width':.8}]})
        self.cnc.process_profiles=fixture.profiles
        fixture.cam.current=None
        def program(identity,active,filename):
            kind=fixture.cam.get(identity)['report']['sequence'][0]['kind']
            depth=self.isolation['depth'] if kind=='isolation' else 1.8
            feed=self.isolation['conditions']['feed'] if kind=='isolation' else 17
            plunge=self.isolation['conditions']['plunge'] if kind=='isolation' else 17
            power=self.isolation['conditions']['power'] if kind=='isolation' else 1000
            tag=f"; BARK_BEETLE_PROFILE {self.isolation['id']} {self.isolation['fingerprint']}\n" if kind=='isolation' else ''
            return {'name':'fixture.nc','content':tag+f'G21 G90 G94 G54\nG0 Z3\nG0 X0 Y0\nM3 S{power}\nG1 Z-{depth} F{plunge}\nG1 X10 Y0 F{feed}\nG1 X10 Y10\nG1 X0 Y10\nG0 Z3\nM5\nM30'}
        fixture.cam.program=program
        self.store=PcbProjects(fixture.root/'real-projects',fixture.library,fixture.cam,fixture.profiles,fixture.progress,self.cnc)
        self.run=self.store.create_setup({'packageId':fixture.package['id']})
        self.cnc.project_datum={'id':'fixture-datum','setupId':self.run['id'],'offset':[0,0]}
        self.status_patch=patch.object(self.cnc,'_status');self.status_patch.start();self.addCleanup(self.status_patch.stop)
        def line(command):
            if command=='$#':return ['[G54:'+','.join(str(v) for v in self.cnc.offset)+']','[G92:0,0,0]','[TLO:0]']
            return ['[GC:G0 G54 G21 G90 G94 M5]']
        self.line_patch=patch.object(self.cnc,'_line',side_effect=line);self.line_patch.start();self.addCleanup(self.line_patch.stop)

    def request(self,kind='isolation',**extra):
        profile={'isolation':self.isolation,'drilling':self.fixture.drill,'outline':self.fixture.outline}[kind]
        return {'setupId':self.run['id'],'stage':kind,'thicknessMm':1.6,'profileId':profile['id'],
            'fingerprint':profile['fingerprint'],'confirmed':True,'fixed_probe':True,
            'position':self.cnc.report['position'][:],'columns':3,'rows':3,'distance':1.4,'feed':20,**extra}

    def wait_phase(self,expected):
        for _ in range(100):
            with self.cnc.lock:
                record=self.cnc.project_cycle.status()
                if record['phase']==expected:return record
                if not record['active']:self.fail(str(record))
            time.sleep(.01)
        self.fail(str(self.cnc.project_cycle.status()))

    def receive(self,value):
        self.cnc.port.receive+=value.encode();self.cnc.last_probe.tick(self.cnc)

    def complete_probe(self):
        scan=self.cnc.last_probe
        self.receive('[PRB:0,0,5:1]\nok\n<Idle|MPos:0,0,4.998|Pn:P>\n')
        self.receive('ok\nok\n<Idle|MPos:0,0,6|WCO:0,0,5>\n')
        if scan is self.cnc.surface:
            for point in scan.points:
                x,y=point['x'],point['y']
                self.receive(f'ok\n<Idle|MPos:{x},{y},6|WCO:0,0,5>\n')
                self.receive(f'[PRB:{x},{y},5:1]\nok\n<Idle|MPos:{x},{y},4.998|Pn:P>\n')
                self.receive(f'ok\n<Idle|MPos:{x},{y},6|WCO:0,0,5>\n')
        self.assertEqual(scan.state,'completed')

    def test_execute_prepares_then_maps_then_queues_one_compensated_cut(self):
        result=self.store.execute(self.request())
        self.wait_phase('probing')
        self.assertEqual(self.cnc.surface.columns,3)
        self.assertNotIn('lease',self.cnc.status()['project_cycle'])
        self.cnc.action('project_cycle_heartbeat',{'lease':result['project_cycle_lease']})
        self.complete_probe();self.cnc.project_cycle.tick(self.cnc)
        self.assertEqual(self.cnc.project_cycle.record['phase'],'cutting')
        self.assertTrue(self.cnc.jobs.active());self.assertTrue(self.cnc.jobs.status()['compensated'])
        job=self.cnc.jobs.job_id;self.cnc.project_cycle.tick(self.cnc)
        self.assertEqual(self.cnc.jobs.job_id,job)
        self.cnc.jobs.state='completed';self.cnc.project_cycle.tick(self.cnc)
        self.assertEqual(self.cnc.project_cycle.record['phase'],'completed')

    def test_drilling_runs_only_one_diameter_and_requires_another_explicit_start(self):
        self.store.execute(self.request('drilling'));self.wait_phase('probing')
        self.assertIs(self.cnc.last_probe,self.cnc.probe)
        self.complete_probe();self.cnc.project_cycle.tick(self.cnc)
        self.assertTrue(self.cnc.jobs.active())
        self.cnc.jobs.state='completed';self.cnc.project_cycle.tick(self.cnc)
        state=self.store.state(self.store.read(self.run['id']))
        self.assertEqual(state['stageStates']['drilling']['index'],1)
        self.assertFalse(state['stageStates']['drilling']['done'])
        self.assertFalse(self.cnc.project_cycle.active())

    def test_measure_only_without_thickness_or_cam_never_starts_job(self):
        self.store.execute(self.request(),True);self.wait_phase('probing')
        self.assertEqual(self.fixture.cam.items,{})
        self.assertIsNone(self.store.read(self.run['id'])['thicknessMm'])
        self.complete_probe();self.cnc.project_cycle.tick(self.cnc)
        self.assertEqual(self.cnc.project_cycle.record['phase'],'measured')
        self.assertFalse(self.cnc.jobs.active());self.assertIsNone(self.cnc.surface.job_id)
        self.assertFalse(any(b'M3' in command for command in self.cnc.port.writes))

    def test_outline_uses_eight_frame_points_then_starts_mapped_cut(self):
        self.store.execute(self.request('outline'));self.wait_phase('probing')
        self.assertTrue(self.cnc.surface.perimeter)
        self.assertEqual(len(self.cnc.surface.points),8)
        self.complete_probe();self.cnc.project_cycle.tick(self.cnc)
        self.assertEqual(self.cnc.project_cycle.record['phase'],'cutting')
        self.assertTrue(self.cnc.jobs.status()['compensated'])

    def test_failed_cam_is_not_retried_or_allowed_to_probe(self):
        start=self.fixture.cam.start
        def fail(*args):
            item=start(*args);self.fixture.cam.items[item['id']].update(state='failed',error='Invalid geometry')
            return item
        self.fixture.cam.start=fail
        self.store.execute(self.request())
        for _ in range(100):
            if not self.cnc.project_cycle.active():break
            time.sleep(.01)
        self.assertEqual(self.cnc.project_cycle.record['phase'],'failed')
        self.assertEqual(len(self.fixture.cam.items),1)
        self.assertFalse(self.cnc.last_probe.active());self.assertEqual(self.cnc.port.writes,[])

    def test_changed_datum_after_probe_prevents_start(self):
        self.store.execute(self.request());self.wait_phase('probing')
        self.complete_probe();self.cnc.project_datum=None
        self.cnc.project_cycle.tick(self.cnc)
        self.assertFalse(self.cnc.jobs.active())
        self.assertEqual(self.cnc.project_cycle.record['phase'],'failed')

    def test_stop_and_expired_owner_cannot_transition_to_cut(self):
        self.store.execute(self.request());self.wait_phase('probing')
        with self.assertRaises(ValueError):self.cnc.action('project_cycle_heartbeat',{'lease':'observer'})
        with self.assertRaises(ValueError):self.cnc.action('zero_xy',{})
        self.complete_probe();self.cnc.project_cycle.heartbeat_at=time.monotonic()-9
        self.cnc.project_cycle.tick(self.cnc)
        self.assertFalse(self.cnc.jobs.active());self.assertEqual(self.cnc.project_cycle.record['phase'],'failed')

    def test_stop_before_cam_finishes_and_profile_change_are_rejected(self):
        self.fixture.cam.current='another-computation'
        self.store.execute(self.request())
        self.cnc.action('project_cycle_stop',{})
        self.fixture.cam.current=None;time.sleep(.25)
        self.assertFalse(self.cnc.project_cycle.active());self.assertEqual(self.cnc.project_cycle.record['phase'],'stopped')
        self.assertFalse(self.cnc.last_probe.active());self.assertEqual(self.cnc.port.writes,[])

    def test_bad_confirmation_and_changed_xy_are_rejected_before_any_commands(self):
        for extra in ({'confirmed':False},{'fixed_probe':False},{'position':[1,0,1]}):
            with self.assertRaises(ValueError):self.store.execute(self.request(**extra))
        self.cnc.project_datum=None
        with self.assertRaises(ValueError):self.store.execute(self.request())
        self.assertEqual(self.cnc.port.writes,[])

if __name__=='__main__':unittest.main()
