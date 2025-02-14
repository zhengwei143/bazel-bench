# Copyright 2019 The Bazel Authors. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http:#www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for the main benchmarking script."""
import mock
import sys
import benchmark
import six

from absl.testing import absltest
from absl.testing import flagsaver
from absl import flags
from testutils.fakes import fake_log, fake_exec_command, FakeBazel

# Setup custom fakes/mocks.
benchmark.logger.log = fake_log
benchmark._exec_command = fake_exec_command
benchmark.Bazel = FakeBazel
mock_stdio_type = six.StringIO


class BenchmarkFunctionTests(absltest.TestCase):

  @mock.patch.object(benchmark.os.path, 'exists', return_value=True)
  @mock.patch.object(benchmark.os, 'chdir')
  def test_setup_project_repo_exists(self, unused_chdir_mock,
                                     unused_exists_mock):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr, \
      mock.patch('benchmark.git.Repo') as mock_repo_class:
      mock_repo = mock_repo_class.return_value
      benchmark._setup_project_repo('repo_path', 'project_source')

    mock_repo.git.fetch.assert_called_once_with('origin')
    self.assertEqual('Path repo_path exists. Updating...',
                     mock_stderr.getvalue())

  @mock.patch.object(benchmark.os.path, 'exists', return_value=False)
  @mock.patch.object(benchmark.os, 'chdir')
  def test_setup_project_repo_not_exists(self, unused_chdir_mock,
                                         unused_exists_mock):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr, \
      mock.patch('benchmark.git.Repo') as mock_repo_class:
      benchmark._setup_project_repo('repo_path', 'project_source')

    mock_repo_class.clone_from.assert_called_once_with('project_source',
                                                       'repo_path')
    self.assertEqual('Cloning project_source to repo_path...',
                     mock_stderr.getvalue())

  def test_get_commits_topological(self):
    with mock.patch('benchmark.git.Repo') as mock_repo_class:
      mock_repo = mock_repo_class.return_value
      mock_A = mock.MagicMock()
      mock_A.hexsha = 'A'
      mock_B = mock.MagicMock()
      mock_B.hexsha = 'B'
      mock_C = mock.MagicMock()
      mock_C.hexsha = 'C'
      mock_repo.iter_commits.return_value = [mock_C, mock_B, mock_A]
      mock_repo.git.rev_parse.side_effect = lambda x: x
      result = benchmark._get_commits_topological(['B', 'A'], mock_repo,
                                                  'flag_name')

      self.assertEqual(['A', 'B'], result)

  def test_get_commits_topological_latest(self):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr, \
      mock.patch('benchmark.git.Repo') as mock_repo_class:
      mock_repo = mock_repo_class.return_value
      mock_commit = mock.MagicMock()
      mock_repo.commit.return_value = mock_commit
      mock_commit.hexsha = 'A'
      result = benchmark._get_commits_topological(None, mock_repo,
                                                  'bazel_commits')

    self.assertEqual(['A'], result)
    self.assertEqual('No bazel_commits specified, using the latest one: A',
                     mock_stderr.getvalue())

  @mock.patch.object(benchmark.os.path, 'exists', return_value=True)
  @mock.patch.object(benchmark.os, 'makedirs')
  def test_build_bazel_binary_exists(self, unused_chdir_mock,
                                     unused_exists_mock):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._build_bazel_binary('commit', 'repo_path', 'outroot')
    self.assertEqual('Binary exists at outroot/commit/bazel, reusing...',
                     mock_stderr.getvalue())

  @mock.patch.object(benchmark.os.path, 'exists', return_value=False)
  @mock.patch.object(benchmark.os, 'makedirs')
  @mock.patch.object(benchmark.os, 'chdir')
  @mock.patch.object(benchmark.shutil, 'copyfile')
  def test_build_bazel_binary_not_exists(self, unused_shutil_mock,
                                         unused_chdir_mock,
                                         unused_makedirs_mock,
                                         unused_exists_mock):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr, \
      mock.patch('benchmark.git.Repo') as mock_repo_class:
      mock_repo = mock_repo_class.return_value
      benchmark._build_bazel_binary('commit', mock_repo, 'outroot')

    mock_repo.git.checkout.assert_called_once_with('-f', 'commit')
    self.assertEqual(
        ''.join([
            'Building Bazel binary at commit commit', 'bazel build //src:bazel',
            'Copying bazel binary to outroot/commit/bazel',
            'chmod +x outroot/commit/bazel'
        ]), mock_stderr.getvalue())

  def test_single_run(self):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._single_run(
          'bazel_binary_path',
          'build',
          options=[],
          targets=['//:all'],
          startup_options=[])

    self.assertEqual(
        ''.join([
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown '
        ]), mock_stderr.getvalue())

  @mock.patch.object(benchmark.os, 'chdir')
  def test_run_benchmark_no_prefetch(self, _):
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._run_benchmark(
          'bazel_binary_path',
          'project_path',
          runs=2,
          bazel_bench_uid='fake_uid',
          command='build',
          options=[],
          targets=['//:all'],
          startup_options=[],
          prefetch_ext_deps=False,
          unit_num=0)

    self.assertEqual(
        ''.join([
            '=== BENCHMARKING BAZEL [Unit #0]: None, PROJECT: None ===',
            'Starting benchmark run 1/2:',
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown ',
            'Starting benchmark run 2/2:',
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown '
        ]), mock_stderr.getvalue())

  @mock.patch.object(benchmark.os, 'chdir')
  def test_run_benchmark_prefetch(self, _):
    benchmark.DEFAULT_OUT_BASE_PATH = 'some_out_path'
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._run_benchmark(
          'bazel_binary_path',
          'project_path',
          runs=2,
          bazel_bench_uid='fake_uid',
          command='build',
          options=[],
          targets=['//:all'],
          startup_options=[],
          prefetch_ext_deps=True,
          unit_num=0)

    self.assertEqual(
        ''.join([
            '=== BENCHMARKING BAZEL [Unit #0]: None, PROJECT: None ===',
            'Pre-fetching external dependencies...',
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown ',
            'Starting benchmark run 1/2:',
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown ',
            'Starting benchmark run 2/2:',
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown '
        ]), mock_stderr.getvalue())

  @mock.patch.object(benchmark.os, 'chdir')
  def test_run_benchmark_collect_profile(self, _):
    benchmark.DEFAULT_OUT_BASE_PATH = 'some_out_path'
    with mock.patch.object(sys, 'stderr', new=mock_stdio_type()) as mock_stderr:
      benchmark._run_benchmark(
          'bazel_binary_path',
          'project_path',
          runs=2,
          bazel_bench_uid='fake_uid',
          command='build',
          options=[],
          targets=['//:all'],
          startup_options=[],
          prefetch_ext_deps=True,
          collect_profile=True,
          data_directory='fake_dir',
          bazel_identifier='fake_bazel_commit',
          project_commit='fake_project_commit',
          unit_num=0)

    self.assertEqual(
        ''.join([
            '=== BENCHMARKING BAZEL [Unit #0]: fake_bazel_commit, PROJECT: fake_project_commit ===',
            'Pre-fetching external dependencies...',
            'Executing Bazel command: bazel build --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown ',
            'Starting benchmark run 1/2:',
            'Executing Bazel command: bazel build --experimental_generate_json_trace_profile --profile=fake_dir/fake_uid_fake_bazel_commit_0_fake_project_commit_1_of_2.profile.gz --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown ',
            'Starting benchmark run 2/2:',
            'Executing Bazel command: bazel build --experimental_generate_json_trace_profile --profile=fake_dir/fake_uid_fake_bazel_commit_0_fake_project_commit_2_of_2.profile.gz --nostamp --noshow_progress --color=no //:all',
            'Executing Bazel command: bazel clean --color=no',
            'Executing Bazel command: bazel shutdown '
        ]), mock_stderr.getvalue())


class BenchmarkFlagsTest(absltest.TestCase):

  @flagsaver.flagsaver
  def test_project_source_present(self):
    # This mirrors the requirement in benchmark.py
    flags.mark_flag_as_required('project_source')
    # Assert that the script fails when no project_source is specified
    with mock.patch.object(
        sys, 'stderr', new=mock_stdio_type()) as mock_stderr, self.assertRaises(
            SystemExit) as context:
      benchmark.app.run(benchmark.main)
    self.assertIn(
        ''.join([
            'FATAL Flags parsing error: flag --project_source=None: ',
            'Flag --project_source must have a value other than None.'
        ]), mock_stderr.getvalue())

  @flagsaver.flagsaver(bazel_commits=['a', 'b'], project_commits=['c', 'd'])
  def test_either_bazel_commits_project_commits_single_element(self):
    with self.assertRaises(ValueError) as context:
      benchmark._flag_checks()
    value_err = context.exception
    self.assertEqual(
        str(value_err),
        'Either --bazel_commits or --project_commits should be a single element.'
    )


if __name__ == '__main__':
  absltest.main()
