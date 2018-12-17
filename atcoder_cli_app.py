import os
import time
import configparser
import requests
import subprocess
import winsound
from bs4 import BeautifulSoup
from pathlib import Path
import colorama
from colorama import Fore, Back, Style

# 問題点
# ARC併設のABCに対応できてない(途中からarcに変わるので)
# 提出した後のフィードバック待ちは非同期にしたいなあ
# けど非同期にすると提出の結果が分かった瞬間に、結果表示が入力待ちとかに割り込む形になっちゃうのかなあ……
# だとすると結構厄介？


class AtCoderCLIApp:
    session = requests.session()
    user_name = None
    password = None
    default_language = None
    last_contest_name = None
    ac_wav = 'ac.wav'
    wa_wav = 'wa.wav'

    # C++, dmd, ldc, Python3, Pypy3 での提出に対応
    language_ids = {'cpp': '3003',
                    'dmd': '3009',
                    'ldc': '3010',
                    'python': '3023',
                    'pypy': '3510'}
    language_ext = {'cpp': '.cpp',
                    'dmd': '.d',
                    'ldc': '.d',
                    'python': '.py',
                    'pypy': '.py'}

    def __init__(self):
        if not Path('./atcoder_cli_app.ini').exists():
            raise FileNotFoundError('iniファイルが存在しません')

        config = configparser.ConfigParser()
        config.read('atcoder_cli_app.ini')

        self.user_name = config['General']['user_name']
        self.password = config['General']['password']
        self.default_language = config['General']['default_language']

        if 'last_contest_name' in config['General']:
            self.last_contest_name = config['General']['last_contest_name']

    def start(self):
        while True:
            try:
                command = input('$ ').split()
            except KeyboardInterrupt:
                # Ctrl+C でもErrorを出さずに抜けられるように
                print()
                return

            # 空文字列のとき
            if not command:
                continue

            if command[0] in {'fetch', 'f'}:
                if len(command) < 2:
                    print('コンテスト名を引数に与えてね')
                    continue
                contest_name = command[1]
                self.fetch_test_cases(contest_name)
            elif command[0] in {'make', 'm'}:
                if len(command) < 2:
                    print('タスク番号を引数に与えてね')
                    continue
                task_number = command[1]
                self.make_test_case(task_number)
            elif command[0] in {'test', 't'}:
                if len(command) < 2:
                    print('タスク番号を引数に与えてね')
                    continue
                task_number = command[1]
                self.run_test(task_number)
            elif command[0] in {'submit', 's'}:
                if len(command) < 2:
                    print('タスク番号を引数に与えてね')
                    continue
                task_number = command[1]
                self.submit(task_number)
            elif command[0] == 'set':
                if len(command) < 2:
                    print('コンテスト名を引数に与えてね')
                    continue
                self.set_contest_name(command[1])
            elif command[0] == 'exit':
                return
            else:
                continue

    def login(self):
        login_url = 'https://practice.contest.atcoder.jp/login'

        login_info = {
            'name': self.user_name,
            'password': self.password
        }

        res = self.session.post(login_url, data=login_info)

        if res.url == 'https://practice.contest.atcoder.jp/login':
            raise LoginError('ログインに失敗しました')

    def submit(self, task_number, language=''):
        if self.last_contest_name is None:
            print('先にコンテスト名を指定してfetchしてください')
            return

        contest_name = self.last_contest_name
        contest_url = 'https://' + contest_name + '.contest.atcoder.jp'
        self.login()

        submit_url = contest_url + '/submit'
        res = self.session.get(submit_url)
        soup = BeautifulSoup(res.text, 'lxml')

        selector = soup.find('select', attrs={'id': 'submit-task-selector'})
        task_ids = [x.get('value') for x in selector.find_all('option')]

        __session = soup.find('input').get('value')
        selected_task_id = task_ids[ord(task_number) - ord('a')]

        submit_info = {'__session': __session,
                       'task_id': selected_task_id
                       }

        params = {'task_id': selected_task_id}

        if not language:
            language = self.default_language

        for task_id in task_ids:
            if task_id == selected_task_id:
                submit_info['language_id_' +
                            task_id] = self.language_ids[language]
            else:
                submit_info['language_id_' + task_id] = '3003'  # C++(何でもいいぽい?)

        p = Path('./' + task_number + self.language_ext[language])

        if not p.exists():
            print(p.name + 'が存在しません')
            return

        source_code = p.read_text(encoding='utf-8')
        submit_info['source_code'] = source_code

        res = self.session.post(submit_url, params=params, data=submit_info)
        submitted_url = contest_url + '/submissions/me'

        if not res.url.startswith(submitted_url):
            print('提出に失敗したかも?')

    def set_contest_name(self, contest_name):
        self.last_contest_name = contest_name

        # ini ファイルにも保存
        config = configparser.ConfigParser()
        config.read('atcoder_cli_app.ini')
        config['General']['last_contest_name'] = contest_name
        with open('atcoder_cli_app.ini', 'w') as config_file:
            config.write(config_file)

    def exists_contest_page(self, contest_name) -> bool:
        contest_url = 'https://' + contest_name + '.contest.atcoder.jp'
        res = self.session.get(contest_url)
        soup = BeautifulSoup(res.text, 'lxml')
        is_404 = (soup.find('title').string[:3] == '404')
        return (not is_404)

    def fetch_test_cases(self, contest_name):
        # コンテスト名だけじゃなくて、URLコピペでも指定できるようにしたいよね

        if not self.exists_contest_page(contest_name):
            print(contest_name + 'というコンテストが存在しません')
            return
        try:
            os.mkdir(contest_name)
        except FileExistsError:
            print('既に同じ名前のファイルが存在します')
            print('そのまま上書きします')

        self.set_contest_name(contest_name)
        self.login()

        contest_url = 'https://' + contest_name + '.contest.atcoder.jp'

        for task_number in 'abcdefgh':
            # https://code-thanks-festival-2018.contest.atcoder.jp/tasks/code_thanks_festival_2018_a
            # などを見ると、なぜか-は_に置き換えなければいけないようだ
            modified_contest_name = contest_name.replace('-', '_')
            task_url = contest_url + '/tasks/' + modified_contest_name + '_' + task_number
            res = self.session.get(task_url)
            soup = BeautifulSoup(res.text, 'lxml')

            # 「提出する」ボタンがあるかどうかで、その問題ページが存在するかを判定している
            exists_submit_button = soup.find(
                'a', attrs={'class': 'btn btn-primary btn-large'}) is not None

            if not exists_submit_button:
                break

            # "Problem Statement" があるかどうかで、英語問題文が用意されているか判定する
            exists_english_statement = (
                res.text.find('Problem Statement') >= 0)

            # サンプルはpreタグで囲われているのでそれを取ってくる
            samples = soup.find_all('pre')
            N = len(samples)

            if exists_english_statement:
                # 英語の部分が重複するので捨てる
                samples = samples[:N//2]

            # 入出力の記法に関する部分を除く(varタグで入れ子になっているのは消す)
            while samples and samples[0].string is None:
                samples = samples[1:]

            # print(samples, sep='\n')

            for i, sample in enumerate(samples):
                file_path = contest_name + '/sample_' + task_number
                file_path += '_' + str(i // 2)
                file_path += '.in' if i % 2 == 0 else '.out'

                lines = sample.string.splitlines()
                # print(lines)

                with open(file_path, mode='w') as f:
                    for line in lines:
                        f.write(line.strip() + '\n')

            print('Fetched sample cases in ' + task_number.upper())

            # print(samples)

            time.sleep(1)

        print('サンプルケースのダウンロードが完了しました!')

    def make_test_case(self, task_number):
        if self.last_contest_name is None:
            print('コンテスト名が指定されていません')
            return

        # 一応これで再起動問題はクリアしてるけど歯抜けになる可能性があるな
        # 0, 1, 3とか、まあそこは大きな問題では無いけど……

        p = Path('./' + self.last_contest_name)

        try:
            max_custom_number = max(
                int(x.stem[9:]) for x in p.iterdir() if x.name.find('custom') >= 0)
        except ValueError:
            max_custom_number = -1

        next_custom_number = max_custom_number + 1

        dir_path = self.last_contest_name

        print('Input')
        print('-'*20)

        input_data = ''

        while True:
            line = input()
            if not line:
                break
            input_data += line + '\n'

        print('Output')
        print('-'*20)

        output_data = ''

        while True:
            line = input()
            if not line:
                break
            output_data += line + '\n'

        ans = input('これでいい? [y/n] ')

        if ans in {'n', 'N', 'no', 'No', 'NO'}:
            return

        file_path = dir_path + '/custom_' + task_number
        file_path += '_' + str(next_custom_number)
        file_path += '.in'

        with open(file_path, mode='w') as f:
            f.write(input_data)

        print('Made ' + file_path)

        file_path = dir_path + '/custom_' + task_number
        file_path += '_' + str(next_custom_number)
        file_path += '.out'

        with open(file_path, mode='w') as f:
            f.write(output_data)

        print('Made ' + file_path)

        print('Done!')

    def run_test(self, task_number):
        if self.last_contest_name is None:
            print('先にコンテスト名を指定してfetchしてください')
            return

        contest_name = self.last_contest_name

        p = Path('./' + contest_name)
        sample_ins = [x for x in p.iterdir() if x.name[7] ==
                      task_number and x.suffix == '.in']

        accepted = True
        for sample_in in sample_ins:
            with sample_in.open() as f:
                try:
                    proc = subprocess.run(
                        [task_number + ".exe"], stdin=f, stdout=subprocess.PIPE)
                except FileNotFoundError:
                    print('実行ファイルが存在しないよ、コンパイルし忘れてる？')
                    return

            actual = [line.strip()
                      for line in proc.stdout.decode('utf-8').splitlines()]
            # print(actual)

            sample_out = Path('./' + contest_name + '/' +
                              sample_in.stem + '.out')
            expect = [line.strip()
                      for line in sample_out.read_text().splitlines()]

            print('-'*5 + sample_in.name + '-'*5)
            print('expect:')
            print(*expect, sep='\n')

            print('actual:')
            print(*actual, sep='\n')

            # print(actual)
            # print(expect)
            ok = actual == expect
            print(Fore.GREEN + 'OK' if ok else Fore.RED + 'NG')
            print()
            accepted = accepted and ok

        # 非同期で効果音を鳴らす
        sound_effect_path = './se/' + \
            (self.ac_wav if accepted else self.wa_wav)
        winsound.PlaySound(sound_effect_path,
                           winsound.SND_FILENAME | winsound.SND_ASYNC)

        print(Back.GREEN + 'Accepted!!!' if accepted else Back.RED + 'Wrong Answer')
        print()


class LoginError(Exception):
    def __init__(self, message):
        self.message = message


if __name__ == '__main__':
    colorama.init(autoreset=True)

    acca = AtCoderCLIApp()
    acca.start()
