import requests
import base64
import time
import os
import sys

REPO_NAME = 'shiny-meme'
IS_PRIVATE = False

def get_headers(token):
    return {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }

def get_username(headers):
    response = requests.get('https://api.github.com/user', headers=headers)
    if response.status_code == 200:
        return response.json()['login']
    return None

def get_user_orgs(headers):
    response = requests.get('https://api.github.com/user/orgs', headers=headers)
    if response.status_code == 200:
        return [org['login'] for org in response.json()]
    return []

def create_or_get_repo(repo_name, is_private, headers, target_owner=None, is_org=False):
    url = f'https://api.github.com/orgs/{target_owner}/repos' if is_org else 'https://api.github.com/user/repos'
    
    data = {'name': repo_name, 'private': is_private, 'auto_init': True}
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 201:
        owner = response.json()['owner']['login']
        print(f"   ✅ Repo sukses dibuat: {owner}/{repo_name}")
        return owner
    elif response.status_code == 422:
        print(f"   ⚠️ Repo {target_owner or 'Utama'}/{repo_name} udah ada. Update file...")
        return target_owner if is_org else get_username(headers)
    else:
        print(f"   ❌ Gagal akses repo. Status: {response.status_code}")
        return None

def upload_local_file(owner, repo_name, local_file_path, target_github_path, headers):
    if not os.path.exists(local_file_path):
        return
    print(f"      -> Uploading {local_file_path}...")
    url = f'https://api.github.com/repos/{owner}/{repo_name}/contents/{target_github_path}'
    get_response = requests.get(url, headers=headers)
    sha = get_response.json()['sha'] if get_response.status_code == 200 else None
    
    with open(local_file_path, 'rb') as file:
        encoded_content = base64.b64encode(file.read()).decode('utf-8')
    
    data = {'message': f'Update {local_file_path} via API', 'content': encoded_content, 'branch': 'main'}
    if sha: data['sha'] = sha
    requests.put(url, headers=headers, json=data)

def trigger_workflow(owner, repo_name, workflow_filename, headers):
    print(f"      -> Mengecek status '{workflow_filename}'...")
    runs_url = f'https://api.github.com/repos/{owner}/{repo_name}/actions/workflows/{workflow_filename}/runs'
    runs_response = requests.get(runs_url, headers=headers)
    
    if runs_response.status_code == 200:
        for run in runs_response.json().get('workflow_runs', []):
            if run.get('conclusion') == 'success' or run.get('status') in ['in_progress', 'queued']:
                print("      ⏩ Udah sukses/jalan. Skip trigger manual.")
                return

    print(f"      🚀 Triggering '{workflow_filename}'...")
    dispatch_url = f'https://api.github.com/repos/{owner}/{repo_name}/actions/workflows/{workflow_filename}/dispatches'
    requests.post(dispatch_url, headers=headers, json={'ref': 'main'})

def process_repository(owner, repo_name, headers):
    if owner:
        time.sleep(2) 
        upload_local_file(owner, repo_name, 'main.py', 'main.py', headers)
        upload_local_file(owner, repo_name, 'requirements.txt', 'requirements.txt', headers)
        upload_local_file(owner, repo_name, 'run.yml', '.github/workflows/run.yml', headers)
        
        time.sleep(3)
        trigger_workflow(owner, repo_name, 'run.yml', headers)

def run_deploy_for_token(token, index, label_akun):
    headers = get_headers(token)
    username = get_username(headers)
    
    print(f"\n==========================================")
    if not username:
        print(f"[{index}] ❌ Token INVALID atau kedaluwarsa: {label_akun} ({token[:10]}...)")
        return
        
    print(f"[{index}] 👤 Memproses Akun: {username} (Target: {label_akun})")
    
    # 1. Akun Personal
    personal_owner = create_or_get_repo(REPO_NAME, IS_PRIVATE, headers, is_org=False)
    if personal_owner:
        process_repository(personal_owner, REPO_NAME, headers)
        
    # 2. Akun Organisasi
    orgs = get_user_orgs(headers)
    if orgs:
        print(f"   🏢 Ketemu {len(orgs)} Organisasi: {', '.join(orgs)}")
        for org_name in orgs:
            org_owner = create_or_get_repo(REPO_NAME, IS_PRIVATE, headers, target_owner=org_name, is_org=True)
            if org_owner:
                process_repository(org_owner, REPO_NAME, headers)
    else:
        print("   ℹ️ Tidak ada Organisasi ditemukan.")

if __name__ == '__main__':
    # Cek file wajib
    required_files = ['main.py', 'requirements.txt', 'run.yml']
    missing_files = [f for f in required_files if not os.path.exists(f)]
    if missing_files:
        print(f"❌ Error: File wajib hilang: {', '.join(missing_files)}")
        sys.exit(1)

    # Cek dan baca akun.txt / list.txt
    target_file = 'akun.txt' if os.path.exists('akun.txt') else 'list.txt'
    if not os.path.exists(target_file):
        print("❌ Error: File 'akun.txt' atau 'list.txt' tidak ditemukan!")
        sys.exit(1)
        
    with open(target_file, 'r') as file:
        lines = [line.strip() for line in file if line.strip()]
        
    if not lines:
        print(f"❌ Error: '{target_file}' kosong, nggak ada data yang bisa diproses!")
        sys.exit(1)
        
    print(f"🚀 Memulai Auto Deployer | File Target: {target_file} | Total Data: {len(lines)}")
    
    for i, line in enumerate(lines, 1):
        try:
            # Deteksi kalau formatnya multi-pipe (username|password|email|totp|token...)
            if '|' in line:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 5 and (parts[4].startswith('ghp_') or parts[4].startswith('github_pat_')):
                    label_akun = parts[0]
                    token = parts[4]
                else:
                    label_akun = parts[0]
                    token = parts[1]
            else:
                label_akun = "Tanpa Label"
                token = line.strip()
                
            run_deploy_for_token(token, i, label_akun)
        except Exception as e:
            print(f"❌ Error saat memproses data ke-{i}: {e}")
            
    print("\n🎉 SEMUA PROSES SELESAI!")