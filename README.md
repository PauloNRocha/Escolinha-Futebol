# Escolinha de Futebol da Chácara · Projeto Social Meu Primeiro Passo

Sistema web completo para gerenciamento de alunos, turmas, presenças e mensalidades da Escolinha de Futebol da Chácara – Projeto Social Meu Primeiro Passo. Desenvolvido com Python, Flask e SQLite para rodar 100% offline no Windows.

## Recursos principais
- Identidade visual personalizada do E.F.C com fonts locais (Montserrat, Poppins), ícones esportivos e Chart offline.
- Perfis de acesso com níveis pré-definidos (Administrador, Gestor, Instrutor) e gestão de usuários pelo painel
- Autenticação com Flask-Login (usuário padrão `admin` / `admin123`)
- Dashboard com métricas de alunos, turmas, presenças e pagamentos
- Cadastro completo de alunos com exportação em CSV
- Gestão de turmas com categorias, horários e locais
- Registro rápido de presenças por turma e data
- Controle mensal de pagamentos com marcação Pago/Pendente e valores previstos/recebidos
- Gestão diferenciada para alunos do projeto social (isentos de mensalidade) com painel dedicado
- Painel financeiro dedicado com vencimentos da semana, atrasados e histórico dos últimos meses
- Área de configurações com troca de senha e backup do banco de dados
- Interface responsiva estilo dashboard com TailwindCSS customizado

## Tecnologias utilizadas
- Python 3
- Flask, Flask-Login, Flask-Bcrypt, Flask-SQLAlchemy
- SQLite (arquivo local `database/escolinha.db`)
- HTML5, Jinja2, TailwindCSS simplificado e JavaScript vanilla

## Instalação (Windows)
1. Instale o [Python 3](https://www.python.org/) se ainda não estiver disponível.
2. Abra o **Prompt de Comando** na pasta do projeto.
3. Crie e ative o ambiente virtual:
   ```bat
   python -m venv venv
   call venv\Scripts\activate
   ```
4. Instale as dependências:
   ```bat
   pip install -r requirements.txt
   ```
5. Inicie o sistema:
   ```bat
   run.bat
   ```
6. Acesse [http://127.0.0.1:5000](http://127.0.0.1:5000) no navegador.

## Estrutura do projeto
```
EscolinhaManager/
├── app.py
├── extensions.py
├── requirements.txt
├── run.bat
├── database/
│   └── escolinha.db (gerado automaticamente)
├── models/
├── templates/
└── static/
```

## Backup do banco de dados
Acesse Configurações → **Fazer backup**. O arquivo será salvo em `database/backups` com data e hora.

## Credenciais iniciais
- Usuário: `admin`
- Senha: `admin123`
> Recomenda-se trocar a senha após o primeiro login (menu Configurações).

## Perfis de acesso
- **Administrador**: acesso completo, pode criar usuários e gerar backups.
- **Gestor**: gerencia alunos, turmas e pagamentos.
- **Instrutor**: registra presenças e consulta o dashboard.

## Suporte e próximos passos
- Cadastre turmas antes de adicionar alunos
- Informe o valor da mensalidade ao cadastrar cada aluno para alimentar os relatórios financeiros
- Configure mensalmente os pagamentos para gerar o histórico
- Utilize a exportação CSV para relatórios externos
