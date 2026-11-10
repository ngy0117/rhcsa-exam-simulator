# RHEL 10 한국어 시험 화면 실습 환경

이 기능은 시험 도중 문제 화면에서 **English / 한국어**를 전환하는 연습 환경입니다.
영어가 기본값이며, 한국어를 선택하면 문제 본문·구성 안내·타이머·완료/재확인 표시가
한국어로 바뀝니다. 시험 시간, 문제 순서, 생성된 값, 표시 상태는 그대로 유지됩니다.
공식 시험 서비스나 공식 시험 문제를 제공하는 것은 아니며, 기존 시뮬레이터의 문제를 사용합니다.

## 준비

RHEL 10 VM 두 대(node1, node2)를 준비합니다. 각 VM에는 약 2 GB 이상의 메모리,
OS용 디스크와 별도의 빈 실습 디스크, 해당 버전의 설치 DVD ISO가 필요합니다.
두 VM은 서로 통신할 수 있어야 합니다. OS는 OS용 디스크에만 설치하십시오.
기존 [두 노드 설치 안내](../SETUP.md)의 사전 조건과 SSH 신뢰 설정을 따릅니다.
아래 명령은 실습용 VM 안에서 실행합니다.

각 VM에 같은 Fork 브랜치를 설치합니다.

```bash
git clone --branch feat/exam-language-ko https://github.com/ngy0117/rhcsa-exam-simulator.git
cd rhcsa-exam-simulator
sudo ./install.sh
```

[SETUP.md의 SSH 설정](../SETUP.md#step-2--passwordless-root-ssh-node1--node2)을 완료한 뒤
각 VM에서 역할과 상대 IP를 지정합니다. 예시 IP는 실제 VM 주소로 바꾸십시오.

```bash
# node1에서: node2의 IP 지정
sudo rhcsa-sim node-setup --role node1 --peer 192.168.100.11

# node2에서: node1의 IP 지정
sudo rhcsa-sim node-setup --role node2 --peer 192.168.100.10

# 양쪽에서 상태 확인
sudo rhcsa-sim doctor
```

## 시험 시작과 언어 선택

node1에서 실행합니다.

```bash
sudo rhcsa-sim start exam-r10-2node-01
sudo rhcsa-sim tui
```

시험 화면 왼쪽 **Select Language / 언어 선택**에서 **한국어**를 선택합니다.
다시 English를 선택하면 영어 원문으로 돌아갑니다. 언어 선택은 브라우저 쿠키에
저장되므로 새로고침과 같은 브라우저의 재접속에도 유지됩니다. 새 브라우저는 영어로
시작합니다. 시험 모드에서는 힌트·해설·풀이 확인 버튼이 표시되지 않으며 해당 API도
기존과 같이 차단됩니다. `--practice`를 추가하지 마십시오.

문제의 지시에 따라 각 노드에서 작업합니다. root 암호 복구 문제는 해당 VM의 콘솔에서
수행해야 합니다. 작업이 끝나면 node1에서 재부팅 후 채점합니다.

```bash
sudo rhcsa-sim grade --reboot
sudo rhcsa-sim report --combined
```

단일 노드로 연습하려면 `exam-r10-01` 또는 `exam-r10-02`를 사용합니다.
다른 두 노드 시험지는 `exam-r10-2node-02`, `exam-r10-2node-03`입니다.

## 번역 범위

저장소에 포함된 RHEL 10 고정 시험지 **5종 전체**, 서로 다른 문제 **65개 전체**의
문제 본문을 한국어로 제공합니다. 각 문항은 영어 원문의 요구 조건, 경로, 사용자명,
암호와 변수 자리표시자를 유지합니다. 번역이 없는 랜덤/추가 문제는 영어로 표시됩니다.
CLI·TUI·연습용 힌트·참고 해설·채점 보고서는 기존 기능을 유지합니다.
OS의 LANG/LC_ALL이나 채점 명령은 변경하지 않습니다.

업데이트 전에 시작한 세션은 매개변수가 들어가는 문제의 한국어 캐시가 없을 수 있으므로
영어로 표시됩니다. 양쪽 VM을 업데이트한 뒤 새 시험을 시작하면 두 언어 캐시가 모두 생성됩니다.
언어를 바꾸기 위해 시험을 다시 시작할 필요는 없습니다.

## 구현과 검증

- `tasks/<id>/prompt.ko-KR.txt`: 한국어 문제. RHEL별 원문이 있으면
  `prompt.rhel10.ko-KR.txt`처럼 같은 버전의 번역만 사용합니다.
- `lib/paper_language.py`: 번역 선택·변수 치환·영어 대체 경로.
- `lib/params.sh:render_prompt()`: 기존 영어 캐시와 별도로 `<id>.ko-KR.txt`를 생성합니다.
  같은 `.env` 값을 사용하며 생성·채점 코드는 실행하지 않습니다.
- 기존 두 노드의 `tar` 전송은 한국어 캐시도 함께 가져옵니다. 웹 서버가 원격 노드의
  매개변수나 새 SSH 접속에 의존하지 않습니다.
- `tui/locales/ko-KR.json`: 시험 화면의 표시 문구. `tr()`은 원본 템플릿을 키로 조회하며
  번역을 찾지 못하면 영어 원문을 반환합니다. 사용자 데이터나 명령 출력은 치환하지 않습니다.
- 웹 요청의 언어는 `ContextVar`로 분리합니다. 동시 브라우저 요청끼리 언어가 섞이지 않습니다.

```bash
python3 -m unittest discover -s tests -p test_paper_language.py -v
bash tests/version_test.sh
```

테스트는 VM이나 root 권한 없이 실행됩니다. 시험지 번역 누락, 변수·경로 보존,
두 노드 캐시 전달, 시간·표시 상태 유지, 언어별 요청 분리와 시험 모드의 학습 기능 차단을
검사합니다. 실제 RHEL VM의 설치·부팅·두 노드 채점은 해당 VM에서 별도로 확인해야 합니다.
