"""Do not hide changed desired state behind default normalization."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]/'hack/restore'))
from compare_defaults import classify, explanation


class ComparisonTests(unittest.TestCase):
    def test_changed_source_and_unknown_additions_fail(self):
        cases = [
            {'path':'/spec/template/spec/containers/0/image', 'change':'changed',
             'expected':'example:v1','actual':'example:v2'},
            {'path':'/metadata/labels/unexpected','change':'added','actual':'x'},
            {'path':'/spec/replicas','change':'missing','expected':3},
            {'path':'/spec/template/spec/dnsPolicy','change':'added','actual':'Default'},
        ]
        for diff in cases:
            result=classify({'objects':[{'identity':['apps/v1','Deployment','leonia','app'],'differences':[diff]}]})
            self.assertEqual(result['exact_ignoring_explained_server_additions'],0)
            self.assertEqual(len(result['unexplained']),1)

    def test_nested_container_defaults_preserve_source_values(self):
        expected=[{'name':'app','image':'example:v1'}]
        actual=[{'name':'app','image':'example:v1','imagePullPolicy':'IfNotPresent'}]
        row={'identity':['apps/v1','Deployment','leonia','app'], 'differences':[
            {'path':'/spec/template/spec/containers','change':'changed','expected':expected,'actual':actual}]}
        self.assertEqual(classify({'objects':[row]})['exact_ignoring_explained_server_additions'],1)
        actual[0]['image']='example:v2'
        self.assertEqual(classify({'objects':[row]})['exact_ignoring_explained_server_additions'],0)

    def test_allocations_are_not_general_field_exemptions(self):
        self.assertIsNotNone(explanation('Service',{'path':'/spec/clusterIP','change':'added','actual':'10.0.0.10'}))
        self.assertIsNone(explanation('ConfigMap',{'path':'/data/clusterIP','change':'added','actual':'10.0.0.10'}))
        self.assertIsNone(explanation('Service',{'path':'/spec/clusterIP','change':'changed','expected':'10.0.0.1','actual':'10.0.0.10'}))


if __name__=='__main__':unittest.main()
