import re
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import os

def extract_loss_data(log_content):
    """从训练日志中提取训练损失和验证损失数据"""
    # 提取训练损失数据的正则表达式
    train_pattern = r'\| epoch\s+(\d+)\s+step\s+(\d+)\s+\|\s+\d+\s+batches\s+\|.*?loss\s+([\d.]+)\s+\|\s+avg loss\s+([\d.]+)'
    train_matches = re.finditer(train_pattern, log_content)
    
    # 提取验证损失数据的正则表达式
    valid_pattern = r'\| Eval\s+(\d+)\s+at step\s+(\d+)\s+\|.*?valid loss\s+([\d.]+)'
    valid_matches = re.finditer(valid_pattern, log_content)
    
    train_data = {
        'steps': [],
        'losses': [],
        'avg_losses': [],
        'epochs': []
    }
    
    valid_data = {
        'steps': [],
        'losses': [],
        'evals': []
    }
    
    for match in train_matches:
        epoch = int(match.group(1))
        step = int(match.group(2))
        loss = float(match.group(3))
        avg_loss = float(match.group(4))
        
        train_data['epochs'].append(epoch)
        train_data['steps'].append(step)
        train_data['losses'].append(loss)
        train_data['avg_losses'].append(avg_loss)
    
    for match in valid_matches:
        eval_num = int(match.group(1))
        step = int(match.group(2))
        loss = float(match.group(3))
        
        valid_data['evals'].append(eval_num)
        valid_data['steps'].append(step)
        valid_data['losses'].append(loss)
    
    return train_data, valid_data

def plot_loss_curve(train_data, valid_data, output_path='training_loss_curve.png'):
    """绘制训练误差曲线"""
    plt.figure(figsize=(12, 6))
    
    plt.plot(train_data['steps'], train_data['losses'], 'b-', alpha=0.3, label='Training Loss')
    plt.plot(train_data['steps'], train_data['avg_losses'], 'b-', label='Training Avg Loss')
    
    plt.plot(valid_data['steps'], valid_data['losses'], 'r-o', label='Validation Loss')
    
    plt.title('Training and Validation Loss Curve')
    plt.xlabel('Training Steps')
    plt.ylabel('Loss')
    
    plt.legend()
    plt.grid(True)
    
    ax = plt.gca()
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    
    plt.tight_layout()
    plt.savefig(output_path)
    print(f"Loss curve saved to {output_path}")
    
    plt.show()

def main():
    log_file = 'training_log_jittor.txt'  # 可替换为training_log_pytorch.txt
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            log_content = f.read()
    except FileNotFoundError:
        print(f"错误: 文件 '{log_file}' 不存在。请确保文件路径正确。")
        return
    
    train_data, valid_data = extract_loss_data(log_content)
    
    output_dir = os.path.dirname(log_file) or '.'
    output_path = os.path.join(output_dir, 'training_loss_curve_jittor.png') # 可替换为training_log_pytorch.png
    plot_loss_curve(train_data, valid_data, output_path)

if __name__ == "__main__":
    main()    